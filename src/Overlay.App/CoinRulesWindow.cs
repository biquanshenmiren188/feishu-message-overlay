using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
namespace Overlay.App;

internal record CoinEdit(string Channel,string Coin,string Exchange,bool? Before,bool? After);
internal static class CoinRuleModel
{
    internal static readonly string[] Channels=["desktop","mute","cards","mobile"];
    internal static readonly string[] Names=["电脑屏蔽","电脑静音","行情卡片","手机推送"];
    internal static readonly string[] Exchanges=["all","binance","okx","bybit","bitget","gate","aster","hyperliquid"];
    internal static readonly string[] ExchangeNames=["全部交易所","Binance","OKX","Bybit","Bitget","Gate","Aster","Hyperliquid"];
    internal static Dictionary<(string Channel,string Exchange),bool> Read(JsonElement data,string coin)
    {
        var desktop=data.GetProperty("desktop");var rules=desktop.GetProperty("desktop").GetProperty("rules");
        var policies=new[]{rules.GetProperty("hide"),rules.GetProperty("mute"),desktop.GetProperty("cards").GetProperty("settings"),data.GetProperty("mobile").GetProperty("settings")};
        var result=new Dictionary<(string,string),bool>();
        for(var i=0;i<Channels.Length;i++)
        {
            var s=policies[i];var channel=Channels[i];
            foreach(var c in s.GetProperty("excluded_coins").EnumerateArray())if(string.Equals(c.GetString(),coin,StringComparison.OrdinalIgnoreCase))result[(channel,"all")]=true;
            if(s.TryGetProperty("advanced",out var advanced)&&advanced.TryGetProperty("coins",out var coins))foreach(var r in coins.EnumerateArray())
                if(string.Equals(r.GetProperty("coin").GetString(),coin,StringComparison.OrdinalIgnoreCase))
                {var k=(channel,r.GetProperty("exchange").GetString()!);result[k]=result.GetValueOrDefault(k)||r.GetProperty("enabled").GetBoolean();}
        }
        return result;
    }
    internal static CoinEdit[] Changes(string coin,Dictionary<(string Channel,string Exchange),bool> before,Dictionary<(string Channel,string Exchange),bool> after)=>before.Keys.Union(after.Keys).Select(k=>new CoinEdit(k.Channel,coin,k.Exchange,before.TryGetValue(k,out var b)?b:null,after.TryGetValue(k,out var a)?a:null)).Where(c=>c.Before!=c.After).ToArray();
}

internal sealed class CoinRulesWindow : Window
{
    private readonly string coin;private readonly bool quick;private readonly Func<object,Task<JsonElement>> transport;
    private readonly StackPanel rows=new();private readonly TextBlock status=new(){TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,10,0,4)};
    private readonly TextBlock review=new(){TextWrapping=TextWrapping.Wrap,Foreground=Brushes.SlateGray,Margin=new Thickness(0,10,0,0)};
    private readonly Button add=Button("＋ 添加交易所范围"),save=Button("保存修改"),block=Button("屏蔽三端"),retry=Button("重试未完成项"),close=Button("关闭");
    private readonly List<(WrapPanel Panel,ComboBox Scope,ComboBox[] Values)> editors=[];
    private Dictionary<(string Channel,string Exchange),bool> baseline=new();private object? pending;private bool busy,loaded;
    internal Task Ready{get;private set;}=Task.CompletedTask;
    internal string Result=>status.Text;
    private static Button Button(string text)=>new(){Content=text,Padding=new Thickness(12,7,12,7),Margin=new Thickness(0,0,8,0),MinHeight=32,Background=Brushes.White,BorderBrush=Brushes.LightSteelBlue};
    internal CoinRulesWindow(string symbol,bool quickBlock=false,Func<object,Task<JsonElement>>? send=null)
    {
        coin=symbol.Trim().ToUpperInvariant();quick=quickBlock;transport=send??Request;
        Title=coin+" · 币种规则";Width=Math.Min(860,SystemParameters.WorkArea.Width-30);Height=Math.Min(440,SystemParameters.WorkArea.Height-30);MinWidth=520;MinHeight=340;FontFamily=new FontFamily("Segoe UI");FontSize=14;Background=Brushes.White;WindowStartupLocation=WindowStartupLocation.CenterOwner;ShowInTaskbar=false;
        var root=new DockPanel{Margin=new Thickness(18)};Content=root;
        var head=new StackPanel();head.Children.Add(new TextBlock{Text=Title,FontSize=21,FontWeight=FontWeights.SemiBold});head.Children.Add(new TextBlock{Text="电脑隐藏、电脑静音、行情卡片和手机推送独立设置。\n手机对应原始管理码方案；隐藏优先于静音。",TextWrapping=TextWrapping.Wrap,Foreground=Brushes.SlateGray,Margin=new Thickness(0,8,0,12)});DockPanel.SetDock(head,Dock.Top);root.Children.Add(head);
        var bottom=new StackPanel();bottom.Children.Add(review);bottom.Children.Add(status);var actions=new WrapPanel{Margin=new Thickness(0,12,0,0)};foreach(var b in new[]{block,close,retry,save})actions.Children.Add(b);bottom.Children.Add(actions);DockPanel.SetDock(bottom,Dock.Bottom);root.Children.Add(bottom);
        var body=new StackPanel();body.Children.Add(rows);add.HorizontalAlignment=HorizontalAlignment.Left;body.Children.Add(add);root.Children.Add(new ScrollViewer{Content=body,VerticalScrollBarVisibility=ScrollBarVisibility.Auto});
        block.Foreground=Brushes.Firebrick;block.ToolTip="立即屏蔽此币种全部交易所的电脑消息、行情卡片和原始管理码手机方案；静音保留";save.Background=new SolidColorBrush(Color.FromRgb(0,117,233));save.Foreground=Brushes.White;
        add.Click+=(_,_)=>{var used=editors.Select(e=>e.Scope.SelectedIndex).ToHashSet();var index=Enumerable.Range(0,CoinRuleModel.Exchanges.Length).FirstOrDefault(i=>!used.Contains(i),-1);if(index>=0)AddRow(CoinRuleModel.Exchanges[index]);};
        close.Click+=(_,_)=>Close();save.Click+=async(_,_)=>await SaveAsync();block.Click+=async(_,_)=>await BlockAsync();retry.Click+=async(_,_)=>{if(pending is {} request)await PerformAsync(request);};
        Closing+=(_,e)=>{if(busy)e.Cancel=true;};Loaded+=(_,_)=>Ready=quick?BlockAsync():LoadAsync();Review();
    }
    private static async Task<JsonElement> Request(object request)
    {
        using var response=await PublicWebPublisher.SendControlAsync("/radar/api/robot-push/control",new{action="coin-rules",request});
        var root=response.RootElement;if(!root.TryGetProperty("ok",out var ok)||!ok.GetBoolean())throw new InvalidOperationException(root.TryGetProperty("error",out var error)?error.GetString():"规则服务暂不可用");
        return root.GetProperty("data").Clone();
    }
    internal static async Task VerifyConnectionAsync(string output)
    {
        var data=await Request(new{op="state"});
        _=CoinRuleModel.Read(data,"CONNECTION_CHECK");
        System.IO.File.WriteAllText(output,JsonSerializer.Serialize(new{connected=true,revision=data.GetProperty("desktop").GetProperty("revision").GetInt32(),phoneRulesAvailable=true,readOnly=true}));
    }
    private void Fill(JsonElement data)
    {
        baseline=CoinRuleModel.Read(data,coin);rows.Children.Clear();editors.Clear();loaded=true;
        var scopes=baseline.Keys.Select(k=>k.Exchange).Distinct().ToArray();foreach(var scope in scopes.Length>0?scopes:["all"])AddRow(scope);Review();
    }
    private void AddRow(string exchange)
    {
        var panel=new WrapPanel{Margin=new Thickness(0,0,0,12)};var scope=new ComboBox{ItemsSource=CoinRuleModel.ExchangeNames,SelectedIndex=Array.IndexOf(CoinRuleModel.Exchanges,exchange),MinHeight=30,Width=136};
        void Field(string label,ComboBox combo){var stack=new StackPanel{Margin=new Thickness(0,0,8,8)};stack.Children.Add(new TextBlock{Text=label,FontSize=12,Margin=new Thickness(0,0,0,5)});stack.Children.Add(combo);panel.Children.Add(stack);combo.SelectionChanged+=(_,_)=>Review();}
        Field("交易所范围",scope);var values=new ComboBox[4];for(var i=0;i<4;i++){var has=baseline.TryGetValue((CoinRuleModel.Channels[i],exchange),out var on);var combo=new ComboBox{ItemsSource=new[]{"未设置","已启用","已停用"},SelectedIndex=has?(on?1:2):0,MinHeight=30,Width=112};values[i]=combo;Field(CoinRuleModel.Names[i],combo);}
        var remove=Button("删除本行");remove.Margin=new Thickness(0,20,0,8);panel.Children.Add(remove);editors.Add((panel,scope,values));rows.Children.Add(panel);remove.Click+=(_,_)=>{editors.RemoveAll(r=>r.Panel==panel);rows.Children.Remove(panel);Review();};Review();
    }
    internal CoinEdit[] Changes()
    {
        var next=new Dictionary<(string Channel,string Exchange),bool>();var scopes=new HashSet<int>();
        foreach(var row in editors){if(row.Scope.SelectedIndex<0||!scopes.Add(row.Scope.SelectedIndex))throw new InvalidOperationException("交易所范围重复，请合并为一行");var exchange=CoinRuleModel.Exchanges[row.Scope.SelectedIndex];for(var i=0;i<4;i++)if(row.Values[i].SelectedIndex>0)next[(CoinRuleModel.Channels[i],exchange)]=row.Values[i].SelectedIndex==1;}
        return CoinRuleModel.Changes(coin,baseline,next);
    }
    private void Review()
    {
        var count=0;var error="";try{count=Changes().Length;}catch(InvalidOperationException e){error=e.Message;}
        review.Text=error.Length>0?error:count>0?$"本次修改 {count} 项，保存后同步生效。":"未设置的渠道可直接启用；删除只影响本币种所选范围。";
        rows.IsEnabled=add.IsEnabled=loaded&&!busy&&pending is null;save.IsEnabled=loaded&&!busy&&pending is null&&error.Length==0&&count>0;block.IsEnabled=!busy&&pending is null&&error.Length==0&&count==0;close.IsEnabled=!busy;retry.Visibility=pending is null?Visibility.Collapsed:Visibility.Visible;retry.IsEnabled=!busy;
    }
    private async Task LoadAsync(){busy=true;Review();status.Text="正在加载云端规则…";try{Fill(await transport(new{op="state"}));status.Text="已加载云端规则";}catch(Exception e){status.Text="加载失败："+SafeError(e)+"。请关闭后重新打开。";}finally{busy=false;Review();}}
    internal Task BlockAsync()=>PerformAsync(new{op="block",request=new{requestId=Guid.NewGuid().ToString("N"),coins=new[]{coin},exchange="all"}});
    internal Task SaveAsync()=>save.IsEnabled?PerformAsync(new{op="edit",request=new{requestId=Guid.NewGuid().ToString("N"),changes=Changes()}}):Task.CompletedTask;
    internal async Task PerformAsync(object request)
    {
        if(busy)return;busy=true;pending=request;Review();status.Text="正在保存…";
        try{var data=await transport(request);var results=data.GetProperty("operation").GetProperty("results");var lines=new List<string>();bool complete=true;foreach(var r in results.EnumerateObject()){var state=r.Value.GetProperty("state").GetString();if(state=="skipped")continue;var i=Array.IndexOf(CoinRuleModel.Channels,r.Name);if(i<0)continue;var ok=state=="saved";complete&=ok;lines.Add(CoinRuleModel.Names[i]+"："+(ok?"已保存":r.Value.TryGetProperty("error",out var error)?error.GetString():"未完成"));}status.Text=string.Join("；",lines)+(complete?"。约 3 秒同步，操作记录已保留。":"。可重试未完成项；规则冲突请关闭后重新管理。");if(complete){pending=null;Fill(data);}}
        catch(Exception e){status.Text=SafeError(e)+"。结果尚未确认，可重试核对；重复请求不会重复修改。";}
        finally{busy=false;Review();}
    }
    private static string SafeError(Exception e)=>e is InvalidOperationException?e.Message:"规则服务暂时不可用";
    internal void SetStateForTest(int row,int channel,int state)=>editors[row].Values[channel].SelectedIndex=state;
}
