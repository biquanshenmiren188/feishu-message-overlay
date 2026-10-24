using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
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
        IEnumerable<T> Children<T>(DependencyObject parent) where T:DependencyObject{for(var i=0;i<VisualTreeHelper.GetChildrenCount(parent);i++){var child=VisualTreeHelper.GetChild(parent,i);if(child is T item)yield return item;foreach(var nested in Children<T>(child))yield return nested;}}
        async Task<CoinRulesWindow> Open(string coin){var w=new CoinRulesWindow(coin,Send){Left=-12000,Top=-12000,WindowStartupLocation=WindowStartupLocation.Manual,ShowActivated=false};w.Show();await w.Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);await w.Ready;return w;}
        Dictionary<(string Channel,string Exchange),bool> Read(string coin)=>CoinRuleModel.Read(JsonSerializer.SerializeToElement(data),coin);
        void Seed(string coin,string channel,string exchange,bool enabled)=>Policy(channel)["advanced"]!["coins"]!.AsArray().Add(new JsonObject{["coin"]=coin,["exchange"]=exchange,["enabled"]=enabled});
        var window=await Open("PTB");
        Check(requests.Count==1,"open only reads existing rules");Check(window.Changes().Length==0,"existing mute loaded unchanged");
        var selectors=Children<ComboBox>(window).ToArray();Check(selectors.Length==4,"one scope and three channel selectors");
        Check(selectors[1].Items.Cast<string>().SequenceEqual(["正常推送","仅静音","屏蔽"]),"desktop labels directly describe normal mute or block");
        Check(selectors.Skip(2).All(s=>s.Items.Cast<string>().SequenceEqual(["正常推送","屏蔽"])),"card and mobile each offer only normal or block");
        Check(!Children<TextBlock>(window).Any(t=>t.Text is "未设置" or "已启用" or "已停用"),"no ambiguous state labels");
        window.SetStateForTest(0,2,1);Check(window.Changes() is [{Channel:"cards",Before:null,After:true}],"card edit does not touch mute or other channels");failNext=true;await window.SaveAsync();var failed=requests.Last();Check(window.Result.Contains("结果尚未确认",StringComparison.Ordinal),"uncertain write is not success");
        using(var request=JsonDocument.Parse(failed))await window.PerformAsync(request.RootElement.Clone());Check(requests.Last()==failed,"retry preserves request identity and exact changes");Check(window.Result.Contains("已保存",StringComparison.Ordinal),"retry success displayed");
        Check(CoinRuleModel.Read(JsonSerializer.SerializeToElement(data),"PTB").Count==2,"saved cards and original mute coexist");
        window.SetStateForTest(0,2,0);await window.SaveAsync();Check(CoinRuleModel.Read(JsonSerializer.SerializeToElement(data),"PTB").Keys.Single().Channel=="mute","delete card rule preserves mute");
        var beforeDraft=requests.Count;await window.BlockAsync();Check(requests.Count==beforeDraft,"block button only stages changes");Check(Read("PTB").Keys.Single().Channel=="mute","draft does not write cloud state");Check(window.Changes().Length==4&&window.Changes().Any(c=>c is {Channel:"mute",Before:true,After:null}),"three channels staged and same-scope mute cleared explicitly");await window.BlockAsync();Check(window.Changes().Length==4,"repeated block does not duplicate scopes");await window.SaveAsync();var result=Read("PTB");Check(new[]{"desktop","cards","mobile"}.All(c=>result[(c,"all")])&&!result.ContainsKey(("mute","all")),"block saves hide cards and mobile without mute");Check(window.Result.Contains("电脑推送：屏蔽；行情卡片：屏蔽；手机推送：屏蔽",StringComparison.Ordinal)&&!window.Result.Contains("仅静音：已保存",StringComparison.Ordinal),"save summary shows current outcomes rather than removed mute");
        window.UpdateLayout();var image=new RenderTargetBitmap((int)Math.Ceiling(window.ActualWidth),(int)Math.Ceiling(window.ActualHeight),96,96,PixelFormats.Pbgra32);image.Render(window);var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(image));using(var stream=File.Create(Path.Combine(directory,"coin-manager-desktop.png")))encoder.Save(stream);window.Close();
        var before=requests.Count;var draft=await Open("ALT");Check(requests.Count==before+1&&requests.Last().Contains("\"op\":\"state\"",StringComparison.Ordinal),"management entrance only reads state");Check(draft.Changes().Length==0,"management entrance does not preselect blocks");await draft.BlockAsync();Check(draft.Changes().Length==3,"internal block stages three changes");Check(draft.Width==640&&draft.Height==340,"compact default window");draft.Close();Check(requests.Count==before+1,"closing draft does not save");draft=await Open("ALT");Check(draft.Changes().Length==0&&Read("ALT").Count==0,"reopening discards the unsaved draft");draft.Close();
        window=await Open("PTB");window.SetStateForTest(0,0,1);Check(window.Changes().Length==2&&window.Changes().Any(c=>c is {Channel:"desktop",Before:true,After:null})&&window.Changes().Any(c=>c is {Channel:"mute",Before:null,After:true}),"only mute precisely replaces desktop block");await window.SaveAsync();
        window.SetStateForTest(0,0,0);Check(window.Changes() is [{Channel:"mute",Before:true,After:null}],"normal desktop removes only mute");await window.SaveAsync();window.SetStateForTest(0,2,0);window.SetStateForTest(0,3,0);Check(window.Changes().Length==2&&window.Changes().All(c=>c.After is null),"normal card and mobile remove only their blocks");await window.SaveAsync();Check(Read("PTB").Count==0&&window.Result.Contains("电脑推送：正常推送；行情卡片：正常推送；手机推送：正常推送",StringComparison.Ordinal),"normal selections leave no blocks and summary confirms all normal");window.Close();
        foreach(var channel in CoinRuleModel.Channels)Seed("PAUSED",channel,"all",false);window=await Open("PAUSED");Check(window.Changes().Length==0,"legacy paused values load without implicit writes");Check(Children<ComboBox>(window).Skip(1).All(s=>Equals(s.SelectedItem,"正常推送")),"legacy paused values show normal mode");window.SetStateForTest(0,2,1);Check(window.Changes() is [{Channel:"cards",Before:false,After:true}],"editing paused card preserves other paused values");await window.SaveAsync();Check(Read("PAUSED")[("desktop","all")]==false&&Read("PAUSED")[("mute","all")]==false&&Read("PAUSED")[("mobile","all")]==false,"unrelated paused states survive save");window.Close();
        Seed("BOTH","desktop","all",true);Seed("BOTH","mute","all",true);window=await Open("BOTH");Check(window.Changes().Length==0&&Equals(Children<ComboBox>(window).ElementAt(1).SelectedItem,"屏蔽"),"legacy dual states show block without implicit writes");window.SetStateForTest(0,3,1);Check(window.Changes() is [{Channel:"mobile",Before:null,After:true}],"unrelated edit preserves legacy desktop dual state");await window.SaveAsync();window.SetStateForTest(0,0,1);Check(window.Changes() is [{Channel:"desktop",Before:true,After:null}],"choosing only mute explicitly clears legacy hide");window.Close();
        Seed("SCOPED","mute","gate",true);Seed("SCOPED","cards","gate",false);window=await Open("SCOPED");await window.BlockAsync();Check(window.Changes().Length==3&&window.Changes().All(c=>c.Exchange=="all"),"all-scope block preserves other scoped rules");window.SetScopeForTest(1,5);Check(!Children<Button>(window).Single(b=>Equals(b.Content,"保存修改")).IsEnabled,"duplicate scope disables save");before=requests.Count;await window.BlockAsync();Check(requests.Count==before,"duplicate scope cannot trigger a write");window.SetScopeForTest(1,0);await window.SaveAsync();Check(window.Result.Contains("已保存 2 个交易所范围。上方各范围已更新为保存后的状态",StringComparison.Ordinal),"multiple scope summary points to each saved row");window.Close();
        var failedLoadReads=0;window=new CoinRulesWindow("DENIED",_=>{failedLoadReads++;throw new InvalidOperationException("推送码已切换或规则连接中断");}){Left=-12000,Top=-12000,WindowStartupLocation=WindowStartupLocation.Manual,ShowActivated=false};window.Show();await window.Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);await window.Ready;Check(failedLoadReads==1&&!Children<Button>(window).Single(b=>Equals(b.Content,"保存修改")).IsEnabled,"failed load or changed identity cannot save");await window.BlockAsync();Check(failedLoadReads==1&&window.Changes().Length==0,"failed load cannot stage or write");window.Close();
        File.WriteAllText(Path.Combine(directory,"coin-rules-contract.json"),JsonSerializer.Serialize(new{passed=true,checks,syntheticOnly=true}));
    }
}
