using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
namespace Overlay.App;
internal static class CoinRulesContract
{
    internal static async Task RunAsync(string directory)
    {
        Directory.CreateDirectory(directory);var checks=new List<string>();void Check(bool ok,string label){if(!ok)throw new InvalidOperationException(label);checks.Add(label);}
        const string settings="{\"excluded_coins\":[],\"advanced\":{\"coins\":[]}}";
        var data=JsonNode.Parse("{\"desktop\":{\"desktop\":{\"rules\":{\"hide\":"+settings+",\"mute\":"+settings+"}},\"cards\":{\"settings\":"+settings+"}},\"mobile\":{\"settings\":"+settings+"}}")!;
        JsonNode Policy(string channel)=>channel=="mobile"?data["mobile"]!["settings"]!:channel=="cards"?data["desktop"]!["cards"]!["settings"]!:data["desktop"]!["desktop"]!["rules"]![channel=="mute"?"mute":"hide"]!;
        Policy("mute")["advanced"]!["coins"]!.AsArray().Add(new JsonObject{["coin"]="PTB",["exchange"]="all",["enabled"]=true});
        var requests=new List<string>();bool failNext=false;
        Task<JsonElement> Send(object request)
        {
            var raw=JsonSerializer.Serialize(request,new JsonSerializerOptions{PropertyNamingPolicy=JsonNamingPolicy.CamelCase});requests.Add(raw);using var parsed=JsonDocument.Parse(raw);var root=parsed.RootElement;var op=root.GetProperty("op").GetString();
            if(failNext){failNext=false;throw new IOException("synthetic interruption");}
            if(op!="state"){
                var results=new JsonObject();foreach(var c in CoinRuleModel.Channels)results[c]=new JsonObject{["state"]="skipped"};
                var changes=op=="block"?new[]{"desktop","cards","mobile"}.Select(c=>new CoinEdit(c,"PTB","all",null,true)).ToArray():JsonSerializer.Deserialize<CoinEdit[]>(root.GetProperty("request").GetProperty("changes").GetRawText(),new JsonSerializerOptions{PropertyNameCaseInsensitive=true})!;
                foreach(var change in changes){var list=Policy(change.Channel)["advanced"]!["coins"]!.AsArray();foreach(var node in list.ToArray())if(node!["coin"]!.GetValue<string>()==change.Coin&&node["exchange"]!.GetValue<string>()==change.Exchange)list.Remove(node);if(change.After.HasValue)list.Add(new JsonObject{["coin"]=change.Coin,["exchange"]=change.Exchange,["enabled"]=change.After.Value});results[change.Channel]=new JsonObject{["state"]="saved"};}
                data["operation"]=new JsonObject{["results"]=results};
            }
            return Task.FromResult(JsonSerializer.SerializeToElement(data));
        }
        var window=new CoinRulesWindow("PTB",false,Send){Left=-12000,Top=-12000,WindowStartupLocation=WindowStartupLocation.Manual,ShowActivated=false};window.Show();await window.Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);await window.Ready;
        Check(requests.Count==1,"open only reads existing rules");Check(window.Changes().Length==0,"existing mute loaded unchanged");
        window.SetStateForTest(0,2,1);Check(window.Changes() is [{Channel:"cards",Before:null,After:true}],"card edit does not touch mute or other channels");failNext=true;await window.SaveAsync();var failed=requests.Last();Check(window.Result.Contains("结果尚未确认",StringComparison.Ordinal),"uncertain write is not success");
        using(var request=JsonDocument.Parse(failed))await window.PerformAsync(request.RootElement.Clone());Check(requests.Last()==failed,"retry preserves request identity and exact changes");Check(window.Result.Contains("已保存",StringComparison.Ordinal),"retry success displayed");
        Check(CoinRuleModel.Read(JsonSerializer.SerializeToElement(data),"PTB").Count==2,"saved cards and original mute coexist");
        window.SetStateForTest(0,2,0);await window.SaveAsync();Check(CoinRuleModel.Read(JsonSerializer.SerializeToElement(data),"PTB").Keys.Single().Channel=="mute","delete card rule preserves mute");
        var beforeDraft=requests.Count;await window.BlockAsync();Check(requests.Count==beforeDraft,"block button only stages changes");Check(CoinRuleModel.Read(JsonSerializer.SerializeToElement(data),"PTB").Keys.Single().Channel=="mute","draft does not write cloud state");Check(window.Changes().Length==3,"three channels staged without changing mute");await window.SaveAsync();var result=CoinRuleModel.Read(JsonSerializer.SerializeToElement(data),"PTB");Check(CoinRuleModel.Channels.All(c=>result[(c,"all")]),"block three retains mute and enables other three");Check(window.Result.Contains("手机推送：已保存",StringComparison.Ordinal),"per-channel result visible");
        window.UpdateLayout();var image=new RenderTargetBitmap((int)Math.Ceiling(window.ActualWidth),(int)Math.Ceiling(window.ActualHeight),96,96,PixelFormats.Pbgra32);image.Render(window);var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(image));using(var stream=File.Create(Path.Combine(directory,"coin-manager-desktop.png")))encoder.Save(stream);window.Close();
        var quick=new CoinRulesWindow("ALT",true,Send){Left=-12000,Top=-12000,WindowStartupLocation=WindowStartupLocation.Manual,ShowActivated=false};var before=requests.Count;quick.Show();await quick.Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);await quick.Ready;Check(requests.Count==before+1&&requests.Last().Contains("\"op\":\"state\"",StringComparison.Ordinal),"card quick action only reads state");Check(quick.Changes().Length==3,"card quick action stages three changes");Check(quick.Width==640&&quick.Height==340,"compact default window");quick.Close();Check(requests.Count==before+1,"closing draft does not save");
        File.WriteAllText(Path.Combine(directory,"coin-rules-contract.json"),JsonSerializer.Serialize(new{passed=true,checks,syntheticOnly=true}));
    }
}
