using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
namespace Overlay.App;

internal record CoinEdit(string Channel,string Coin,string Exchange,bool? Before,bool? After);
internal static class CoinRuleModel
{
    internal static readonly string[] Channels=["desktop","mute","cards","mobile"];
    internal static readonly string[] Names=["电脑屏蔽","仅静音","行情卡片","手机推送"];
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
    private readonly string coin;private readonly Func<object,Task<JsonElement>> transport;
    private readonly StackPanel rows=new();private readonly TextBlock status=new(){TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,10,0,4)};
    private readonly TextBlock review=new(){TextWrapping=TextWrapping.Wrap,Foreground=Brushes.SlateGray,Margin=new Thickness(0,10,0,0)};
    private readonly Button add=Button("＋ 添加交易所范围"),save=Button("保存修改"),block=Button("屏蔽三端"),retry=Button("重试未完成项"),close=Button("关闭");
    private sealed record Editor(WrapPanel Panel,ComboBox Scope,ComboBox Desktop,ComboBox Cards,ComboBox Mobile,bool?[] Values);
    private readonly List<Editor> editors=[];
    private Dictionary<(string Channel,string Exchange),bool> baseline=new();private object? pending;private bool busy,loaded;
    internal Task Ready{get;private set;}=Task.CompletedTask;
    internal string Result=>status.Text;
    private static Button Button(string text)=>new(){Content=text,Padding=new Thickness(8,5,8,5),Margin=new Thickness(0,0,8,0),MinHeight=28,Background=Brushes.White,BorderBrush=Brushes.LightSteelBlue};
    internal CoinRulesWindow(string symbol,Func<object,Task<JsonElement>>? send=null)
    {
        coin=symbol.Trim().ToUpperInvariant();transport=send??Request;
        Title=coin+" · 币种规则";Width=Math.Min(640,SystemParameters.WorkArea.Width-30);Height=Math.Min(340,SystemParameters.WorkArea.Height-30);MinWidth=520;MinHeight=280;FontFamily=new FontFamily("Segoe UI");FontSize=12;Background=Brushes.White;WindowStartupLocation=WindowStartupLocation.CenterOwner;ShowInTaskbar=false;
        var root=new DockPanel{Margin=new Thickness(12)};Content=root;
        var head=new StackPanel();head.Children.Add(new TextBlock{Text=Title,FontSize=18,FontWeight=FontWeights.SemiBold});head.Children.Add(new TextBlock{Text="正常推送：本币种所选范围不屏蔽；仅静音：显示消息但不响。\n屏蔽：不显示消息/卡片或不发手机通知。其他筛选照常生效。",TextWrapping=TextWrapping.Wrap,Foreground=Brushes.SlateGray,Margin=new Thickness(0,8,0,12)});DockPanel.SetDock(head,Dock.Top);root.Children.Add(head);
        var bottom=new StackPanel();bottom.Children.Add(review);bottom.Children.Add(status);var actions=new WrapPanel{Margin=new Thickness(0,12,0,0)};foreach(var b in new[]{block,close,retry,save})actions.Children.Add(b);bottom.Children.Add(actions);DockPanel.SetDock(bottom,Dock.Bottom);root.Children.Add(bottom);
        var body=new StackPanel();body.Children.Add(rows);add.HorizontalAlignment=HorizontalAlignment.Left;body.Children.Add(add);root.Children.Add(new ScrollViewer{Content=body,VerticalScrollBarVisibility=ScrollBarVisibility.Auto});
        block.Foreground=Brushes.Firebrick;block.ToolTip="将电脑消息、行情卡片和手机推送设为屏蔽，点击保存修改后生效";save.Background=new SolidColorBrush(Color.FromRgb(0,117,233));save.Foreground=Brushes.White;
        add.Click+=(_,_)=>{var used=editors.Select(e=>e.Scope.SelectedIndex).ToHashSet();var index=Enumerable.Range(0,CoinRuleModel.Exchanges.Length).FirstOrDefault(i=>!used.Contains(i),-1);if(index>=0)AddRow(CoinRuleModel.Exchanges[index]);};
        close.Click+=(_,_)=>Close();save.Click+=async(_,_)=>await SaveAsync();block.Click+=async(_,_)=>await BlockAsync();retry.Click+=async(_,_)=>{if(pending is {} request)await PerformAsync(request);};
        Closing+=(_,e)=>{if(busy)e.Cancel=true;};Loaded+=(_,_)=>Ready=LoadAsync();Review();
    }
    private static async Task<JsonElement> Request(object request)
    {
        var binding=new DesktopPushBinding(System.IO.Path.Combine(LocalStorage.DirectoryPath,"desktop-push-code.dpapi"));
        if(binding.Code is not {Length:8} code)throw new InvalidOperationException("请先在设置中绑定自己的推送码。");
        using var response=await PublicWebPublisher.SendControlAsync("/radar/api/robot-push/control",new{action="coin-rules",pushCode=code,request});
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
        var panel=new WrapPanel{Margin=new Thickness(0,0,0,12)};var scope=new ComboBox{ItemsSource=CoinRuleModel.ExchangeNames,SelectedIndex=Array.IndexOf(CoinRuleModel.Exchanges,exchange),MinHeight=28,Width=110};
        void Field(string label,ComboBox combo){var stack=new StackPanel{Margin=new Thickness(0,0,8,8)};stack.Children.Add(new TextBlock{Text=label,FontSize=12,Margin=new Thickness(0,0,0,5)});stack.Children.Add(combo);panel.Children.Add(stack);combo.SelectionChanged+=(_,_)=>Review();}
        Field("交易所范围",scope);
        // Retain legacy paused/both-on values until the user changes this field.
        var values=CoinRuleModel.Channels.Select(c=>baseline.TryGetValue((c,exchange),out var on)?(bool?)on:null).ToArray();
        var desktop=new ComboBox{ItemsSource=new[]{"正常推送","仅静音","屏蔽"},SelectedIndex=values[0]==true?2:values[1]==true?1:0,MinHeight=28,Width=118};
        var cards=new ComboBox{ItemsSource=new[]{"正常推送","屏蔽"},SelectedIndex=values[2]==true?1:0,MinHeight=28,Width=82};
        var mobile=new ComboBox{ItemsSource=new[]{"正常推送","屏蔽"},SelectedIndex=values[3]==true?1:0,MinHeight=28,Width=82};
        Field("电脑推送",desktop);Field("行情卡片",cards);Field("手机推送",mobile);
        desktop.SelectionChanged+=(_,_)=>{values[0]=desktop.SelectedIndex==2?true:null;values[1]=desktop.SelectedIndex==1?true:null;Review();};
        cards.SelectionChanged+=(_,_)=>{values[2]=cards.SelectedIndex==1?true:null;Review();};
        mobile.SelectionChanged+=(_,_)=>{values[3]=mobile.SelectedIndex==1?true:null;Review();};
        var remove=Button("删除本行");remove.Margin=new Thickness(0,20,0,8);panel.Children.Add(remove);editors.Add(new(panel,scope,desktop,cards,mobile,values));rows.Children.Add(panel);remove.Click+=(_,_)=>{editors.RemoveAll(r=>r.Panel==panel);rows.Children.Remove(panel);Review();};Review();
    }
    internal CoinEdit[] Changes()
    {
        var next=new Dictionary<(string Channel,string Exchange),bool>();var scopes=new HashSet<int>();
        foreach(var row in editors){if(row.Scope.SelectedIndex<0||!scopes.Add(row.Scope.SelectedIndex))throw new InvalidOperationException("交易所范围重复，请合并为一行");var exchange=CoinRuleModel.Exchanges[row.Scope.SelectedIndex];for(var i=0;i<4;i++)if(row.Values[i] is {} value)next[(CoinRuleModel.Channels[i],exchange)]=value;}
        return CoinRuleModel.Changes(coin,baseline,next);
    }
    private void Review()
    {
        var count=0;var error="";try{count=Changes().Length;}catch(InvalidOperationException e){error=e.Message;}
        review.Text=error.Length>0?error:count>0?$"本次修改 {count} 项，保存后同步生效。":"所有修改均需点击保存才生效；关闭会放弃未保存修改。";
        rows.IsEnabled=add.IsEnabled=loaded&&!busy&&pending is null;save.IsEnabled=loaded&&!busy&&pending is null&&error.Length==0&&count>0;block.IsEnabled=loaded&&!busy&&pending is null&&error.Length==0;close.IsEnabled=!busy;retry.Visibility=pending is null?Visibility.Collapsed:Visibility.Visible;retry.IsEnabled=!busy;
    }
    private async Task LoadAsync(){busy=true;Review();status.Text="正在加载云端规则…";try{Fill(await transport(new{op="state"}));status.Text="上方显示已保存的币种规则。";}catch(Exception e){status.Text="加载失败："+SafeError(e)+"。请关闭后重新打开。";}finally{busy=false;Review();}}
    internal Task BlockAsync()
    {
        if(!loaded||busy||pending is not null||!block.IsEnabled)return Task.CompletedTask;
        if(!editors.Any(e=>e.Scope.SelectedIndex==0))AddRow("all");
        var row=editors.Single(e=>e.Scope.SelectedIndex==0);
        row.Desktop.SelectedIndex=2;row.Values[0]=true;row.Values[1]=null;
        row.Cards.SelectedIndex=row.Mobile.SelectedIndex=1;row.Values[2]=row.Values[3]=true;
        status.Text=Changes().Length>0?"电脑消息、行情卡片、手机推送均已选屏蔽；尚未保存。":"三端已保存为屏蔽，无需重复保存。";Review();return Task.CompletedTask;
    }
    internal Task SaveAsync()=>save.IsEnabled?PerformAsync(new{op="edit",request=new{requestId=Guid.NewGuid().ToString("N"),changes=Changes()}}):Task.CompletedTask;
    internal async Task PerformAsync(object request)
    {
        if(busy)return;busy=true;pending=request;Review();status.Text="正在保存…";
        try{var data=await transport(request);var results=data.GetProperty("operation").GetProperty("results");var lines=new List<string>();bool complete=true;foreach(var r in results.EnumerateObject()){var state=r.Value.GetProperty("state").GetString();if(state=="skipped")continue;var i=Array.IndexOf(CoinRuleModel.Channels,r.Name);if(i<0)continue;var ok=state=="saved";complete&=ok;lines.Add(CoinRuleModel.Names[i]+"："+(ok?"已保存":r.Value.TryGetProperty("error",out var error)?error.GetString():"未完成"));}if(complete){pending=null;Fill(data);status.Text=editors.Count==1?$"已保存。电脑推送：{editors[0].Desktop.SelectedItem}；行情卡片：{editors[0].Cards.SelectedItem}；手机推送：{editors[0].Mobile.SelectedItem}。约 3 秒同步。":$"已保存 {editors.Count} 个交易所范围。上方各范围已更新为保存后的状态，约 3 秒同步。";}else status.Text=string.Join("；",lines)+"。可重试未完成项；规则冲突请关闭后重新管理。";}
        catch(Exception e){status.Text=SafeError(e)+"。结果尚未确认，可重试核对；重复请求不会重复修改。";}
        finally{busy=false;Review();}
    }
    private static string SafeError(Exception e)=>e is InvalidOperationException?e.Message:"规则服务暂时不可用";
    internal void SetStateForTest(int row,int channel,int state)
    {
        var editor=editors[row];
        if(channel==0)editor.Desktop.SelectedIndex=state;
        else if(channel==2)editor.Cards.SelectedIndex=state;
        else if(channel==3)editor.Mobile.SelectedIndex=state;
        else throw new ArgumentOutOfRangeException(nameof(channel));
    }
    internal void SetScopeForTest(int row,int scope)=>editors[row].Scope.SelectedIndex=scope;
    internal void AddScopeForTest(string exchange)=>AddRow(exchange);
}
