using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
namespace Overlay.App;

internal record OpportunityItem(OpportunityBoard Board,OpportunityModel.Entry Entry,DateTimeOffset Now);
public sealed class OpportunityPresenter : ContentControl
{
    public OpportunityPresenter(){HorizontalContentAlignment=HorizontalAlignment.Stretch;DataContextChanged+=(_,_)=>Content=DataContext is OpportunityItem item?item.Board.Build(item.Entry,item.Now):new TextBlock{Text=DataContext as string??"",TextWrapping=TextWrapping.Wrap,Margin=new Thickness(5)};}
}

// The existing signed cloud response carries this credential-free cache. No new upstream poller.
internal sealed class OpportunityModel
{
    internal sealed class Entry(JsonElement data) {internal JsonElement Data=data;internal DateTimeOffset? Missing;}
    internal readonly Dictionary<string,Entry> Cards=new(StringComparer.Ordinal);
    internal DateTimeOffset Sample=DateTimeOffset.MinValue,Received=DateTimeOffset.MinValue;
    internal bool Connected,Complete;
    internal static JsonElement Get(JsonElement value,string name)=>value.ValueKind==JsonValueKind.Object && value.TryGetProperty(name,out var result)?result:default;
    internal static string Text(JsonElement value,string name)=>Get(value,name) is {ValueKind:JsonValueKind.String} result?(result.GetString()??""):"";
    internal static double? Number(JsonElement value,string name)=>Get(value,name) is {ValueKind:JsonValueKind.Number} result && result.TryGetDouble(out var n)&&double.IsFinite(n)?n:null;
    internal static DateTimeOffset Date(JsonElement value,string name)=>DateTimeOffset.TryParse(Text(value,name),CultureInfo.InvariantCulture,DateTimeStyles.RoundtripKind,out var date)?date:DateTimeOffset.MinValue;
    internal static JsonElement[] Array(JsonElement value,string name,int limit)=>Get(value,name) is {ValueKind:JsonValueKind.Array} result?result.EnumerateArray().Take(limit).ToArray():[];
    internal static bool True(JsonElement value,string name)=>Get(value,name).ValueKind==JsonValueKind.True;
    internal static string Percent(double? n,double divisor=100)=>n is {} value?(value>=0?"+":"")+(value/divisor).ToString("0.00",CultureInfo.InvariantCulture)+"%":"—";
    internal static string Money(double? n)=>n is {} value?(value>=1e9?(value/1e9).ToString("0.00",CultureInfo.InvariantCulture)+"B":value>=1e6?(value/1e6).ToString("0.00",CultureInfo.InvariantCulture)+"M":value>=1e3?(value/1e3).ToString("0.00",CultureInfo.InvariantCulture)+"K":value.ToString("0.00",CultureInfo.InvariantCulture)):"—";
    internal static string Asset(JsonElement data)=>Text(data,"asset").Split(':').LastOrDefault() is {Length:>0} name?name:"未知";
    internal static string? Radar(JsonElement data)=>Uri.TryCreate(Text(data,"radarUrl"),UriKind.Absolute,out var uri)&&uri.Scheme=="https"&&uri.Host=="leida.shenmiren.work"&&uri.IsDefaultPort&&uri.AbsolutePath=="/radar/"&&uri.UserInfo.Length==0?uri.AbsoluteUri:null;
    internal void Ingest(JsonElement? envelope,bool transportHealthy,DateTimeOffset now)
    {
        Connected=false;
        if(envelope is not {} value)return;
        var snapshot=Get(value,"snapshot");var sample=Date(snapshot,"sampledAt");
        Received=Date(value,"receivedAt");Complete=True(snapshot,"complete");
        Connected=transportHealthy&&Text(value,"status")=="connected"&&Received<=now.AddSeconds(30)&&sample<=now.AddSeconds(30)&&now-Received<TimeSpan.FromSeconds(20)&&now-sample<TimeSpan.FromSeconds(20);
        if(sample<=Sample||sample>now.AddSeconds(30)||Get(snapshot,"active").ValueKind!=JsonValueKind.Array)return;
        Sample=sample;var present=new HashSet<string>(StringComparer.Ordinal);
        foreach(var data in Array(snapshot,"active",1000))
        {
            var id=Text(data,"id");if(id.Length is 0 or >512||Date(data,"validUntil")==DateTimeOffset.MinValue)continue;
            var pair=Text(data,"pair");var key=pair.Length>0?pair:id;present.Add(key);
            Cards[key]=new(data.Clone());
        }
        if(Complete)foreach(var pair in Cards)if(!present.Contains(pair.Key))pair.Value.Missing??=now;
        Prune(now);
    }
    internal void Prune(DateTimeOffset now)
    {foreach(var pair in Cards.ToArray())if(now>=Expires(pair.Value).AddSeconds(30))Cards.Remove(pair.Key);}
    internal static DateTimeOffset Expires(Entry entry)=>entry.Missing is {} missing && missing<Date(entry.Data,"validUntil")?missing:Date(entry.Data,"validUntil");
    internal string State(Entry entry,DateTimeOffset now)=>entry.Missing is not null?"已失效":!Connected||now-Received>=TimeSpan.FromSeconds(20)||now-Sample>=TimeSpan.FromSeconds(20)?"待恢复":now<Expires(entry)?"ACTIVE":"待确认";
    internal static string? CopyStrategy(JsonElement data)
    {
        var legs=Array(Get(data,"details"),"legs",3);var strategy=Text(data,"strategy");
        if(legs.Length!=2||strategy is not ("SF" or "FS" or "FF"))return null;
        var allowed=new[]{"binance","bitget","bybit","gate","okx","aster","hyperliquid"};
        var buy=Text(legs[0],"exchange");var sell=Text(legs[1],"exchange");
        if(!allowed.Contains(buy)||!allowed.Contains(sell)||strategy=="FS"&&sell is "aster" or "hyperliquid")return null;
        if(True(legs[0],"spot")!=(strategy=="SF")||True(legs[1],"spot")!=(strategy=="FS"))return null;
        string Symbol(JsonElement leg){var s=Text(leg,"symbol").ToUpperInvariant();if(Text(leg,"exchange")=="okx"&&!True(leg,"spot")&&Regex.IsMatch(s,"^[A-Z0-9]+-USDT-SWAP$"))s=s[..^5];return Regex.Replace(s,"[_/\\-]","");}
        var a=Symbol(legs[0]);if(a!=Symbol(legs[1])||!Regex.IsMatch(a,"^[A-Z0-9]+USDT$"))return null;
        var payload=new Dictionary<string,string>{{"type",strategy},{"name",a[..^4]},{"buyEx",buy=="hyperliquid"?"hl":buy},{"sellEx",sell=="hyperliquid"?"hl":sell}};
        if(strategy=="FS")payload["spotMarginType"]="cross";
        return "ASTRO-QUICK-COPY:\n"+JsonSerializer.Serialize(payload,new JsonSerializerOptions{WriteIndented=true});
    }
}

internal sealed class OpportunityBoard : DockPanel
{
    internal readonly OpportunityModel Model=new();
    private readonly TextBlock heading=new(){FontSize=14,FontWeight=FontWeights.SemiBold,Margin=new Thickness(4,6,4,8)};
    private readonly ListBox cards=new(){BorderThickness=new Thickness(0),Background=Brushes.Transparent,HorizontalContentAlignment=HorizontalAlignment.Stretch};
    private string? lastRender;
    internal int ActiveCount{get;private set;}
    internal int VisibleCount{get;private set;}
    internal OpportunityBoard()
    {
        Margin=new Thickness(6,0,6,4);LastChildFill=true;SetDock(heading,Dock.Top);Children.Add(heading);
        ScrollViewer.SetHorizontalScrollBarVisibility(cards,ScrollBarVisibility.Disabled);
        ScrollViewer.SetCanContentScroll(cards,true);VirtualizingPanel.SetIsVirtualizing(cards,true);VirtualizingPanel.SetVirtualizationMode(cards,VirtualizationMode.Recycling);
        var factory=new FrameworkElementFactory(typeof(OpportunityPresenter));cards.ItemTemplate=new DataTemplate{VisualTree=factory};
        var style=new Style(typeof(ListBoxItem));style.Setters.Add(new Setter(Control.HorizontalContentAlignmentProperty,HorizontalAlignment.Stretch));style.Setters.Add(new Setter(Control.PaddingProperty,new Thickness(0)));cards.ItemContainerStyle=style;
        Children.Add(cards);
    }
    private static Brush Brush(string hex)=>new SolidColorBrush((Color)ColorConverter.ConvertFromString(hex));
    private static TextBlock Label(string text,double size=12,bool bold=false,string color="#263238")=>new(){Text=text,TextWrapping=TextWrapping.Wrap,FontSize=size,FontWeight=bold?FontWeights.SemiBold:FontWeights.Normal,Foreground=Brush(color),Margin=new Thickness(1,2,1,2)};
    private static Border Box(UIElement child,string background="#F8FAFB")=>new(){Child=child,Background=Brush(background),BorderBrush=Brush("#DCE3EA"),BorderThickness=new Thickness(.6),CornerRadius=new CornerRadius(4),Padding=new Thickness(7),Margin=new Thickness(0,0,0,7)};
    internal void Update(JsonElement? envelope,bool healthy,DateTimeOffset now,bool visible)
    {
        Model.Ingest(envelope,healthy,now);Model.Prune(now);
        ActiveCount=Model.Cards.Values.Count(c=>Model.State(c,now)=="ACTIVE");
        if(!visible)return;
        // Values are committed at most once per ten seconds; expiry/connection changes remain immediate.
        var ordered=Model.Cards.Values.OrderBy(c=>OpportunityModel.Asset(c.Data),StringComparer.Ordinal).ThenByDescending(c=>OpportunityModel.Number(OpportunityModel.Get(c.Data,"v2Residual"),"level")??-1).ToArray();
        var signature=string.Join('|',ordered.Select(c=>OpportunityModel.Text(c.Data,"id")+Model.State(c,now)))+"/"+now.ToUnixTimeSeconds()/10+"/"+Model.Connected;
        heading.Text=$"卡片推送   {ActiveCount} ACTIVE";
        heading.ToolTip=Model.Connected?$"同步中 · {Model.Sample.ToOffset(TimeSpan.FromHours(8)):HH:mm:ss} UTC+8"+(Model.Complete?"":" · 数据暂不完整"):"正在连接卡片数据源 · 旧数据不计入活跃机会";
        if(signature==lastRender)return;lastRender=signature;VisibleCount=ordered.Length;
        var scroller=FindScroll(cards);var offset=scroller?.VerticalOffset??0;
        cards.ItemsSource=ordered.Length>0?ordered.Select(entry=>(object)new OpportunityItem(this,entry,now)).ToArray():new object[]{Model.Connected?"当前没有活跃机会":"正在连接卡片数据源，恢复后自动显示"};
        if(scroller is not null)Dispatcher.BeginInvoke(System.Windows.Threading.DispatcherPriority.Loaded,new Action(()=>scroller.ScrollToVerticalOffset(offset)));
    }
    internal static ScrollViewer? FindScroll(DependencyObject parent)
    {
        if(parent is ScrollViewer viewer)return viewer;
        for(var i=0;i<VisualTreeHelper.GetChildrenCount(parent);i++)if(FindScroll(VisualTreeHelper.GetChild(parent,i)) is {} child)return child;
        return null;
    }
    internal Border Build(OpportunityModel.Entry entry,DateTimeOffset now)
    {
        var data=entry.Data;var detail=OpportunityModel.Get(data,"details");var residual=OpportunityModel.Get(data,"v2Residual");var level=OpportunityModel.Number(residual,"level");var state=Model.State(entry,now);
        var stack=new StackPanel();
        var title=new DockPanel();var badge=Label($"R{(level?.ToString(CultureInfo.InvariantCulture)??"—")} {OpportunityModel.Percent(OpportunityModel.Number(residual,"bps"))}",12,true);SetDock(badge,Dock.Right);title.Children.Add(badge);title.Children.Add(Label(OpportunityModel.Asset(data)+"  "+OpportunityModel.Text(data,"strategy"),17,true));stack.Children.Add(title);
        var age=Math.Max(0,(int)(now-OpportunityModel.Date(data,"enteredAt")).TotalSeconds);stack.Children.Add(Label(state+(state=="ACTIVE"?$"  {age}s":"")+" · "+(OpportunityModel.Text(data,"trigger")=="v2_price_window"?"V2收敛":OpportunityModel.Text(data,"trigger")),11,true,state=="ACTIVE"?"#28765B":"#A16910"));
        var legs=OpportunityModel.Array(detail,"legs",2);var legGrid=new Grid();legGrid.ColumnDefinitions.Add(new());legGrid.ColumnDefinitions.Add(new());
        for(var i=0;i<legs.Length;i++)
        {
            var leg=legs[i];var spot=OpportunityModel.True(leg,"spot");var panel=new StackPanel{Margin=new Thickness(i==0?0:8,3,0,4)};var exchange=Exchange(leg);
            panel.Children.Add(Label((i==0?"买 ":"卖 ")+exchange+(spot?" 现货":" 永续"),13,true));
            if(!spot)panel.Children.Add(Label(OpportunityModel.Percent(OpportunityModel.Number(leg,"rate"),.01)+"  "+(OpportunityModel.Number(leg,"hours") is {} h?$"{h}h":"—"),19,true));
            panel.Children.Add(Label("24H "+OpportunityModel.Money(OpportunityModel.Number(leg,"volume"))+(!spot?"   OI "+OpportunityModel.Money(OpportunityModel.Number(leg,"oi")):""),10));
            Grid.SetColumn(panel,i);legGrid.Children.Add(panel);
        }stack.Children.Add(legGrid);
        var metrics=new Grid();for(var i=0;i<4;i++)metrics.ColumnDefinitions.Add(new());
        var names=new[]{"净收益均值","盘口差均值","盘口差 P75","指数差均值"};var keys=new[]{"netBps","marketBps","p75Bps","indexBps"};
        for(var i=0;i<4;i++){var column=new StackPanel();column.Children.Add(Label(names[i],10,color:"#536977"));var text=OpportunityModel.Percent(OpportunityModel.Number(detail,keys[i]));column.Children.Add(Label(i==0?text.TrimStart('+'):text,12,true));Grid.SetColumn(column,i);metrics.Children.Add(column);}stack.Children.Add(Box(metrics,"#FFFFFF"));
        var warnings=new List<string>();foreach(var news in OpportunityModel.Array(detail,"newsWarnings",20)){var text=OpportunityModel.Text(news,"summary");if(text.Length>0)warnings.Add(OpportunityModel.Text(news,"exchange").ToUpperInvariant()+" "+text+(OpportunityModel.Text(news,"status")=="postponed"?"（已延期，时间未定）":OpportunityModel.Text(news,"status")=="uncertain"?"（待确认）":""));}
        if(legs.Length==2&&!OpportunityModel.True(legs[0],"spot")&&!OpportunityModel.True(legs[1],"spot")&&OpportunityModel.Number(legs[0],"hours") is >0 and var h0&&OpportunityModel.Number(legs[1],"hours") is >0 and var h1&&h0!=h1)warnings.Add($"周期 {h0}h/{h1}h");
        if(legs.Any(l=>OpportunityModel.Text(l,"exchange")=="bybit"&&!OpportunityModel.True(l,"spot")&&OpportunityModel.Number(l,"hours")==1))warnings.Add("Bybit 1h 计算不同");
        if(warnings.Count>0)stack.Children.Add(Box(Label("⚠ "+string.Join(" · ",warnings),11,true,"#BA2948"),"#FFF0F4"));
        stack.Children.Add(Label("现货充提   充 / 提 · ✓开 ×关 ?未知 —无现货",11,true,"#476371"));
        var transfers=Transfers(legs,OpportunityModel.Array(detail,"transferWallets",20),now);
        foreach(var text in transfers)stack.Children.Add(new Border{Child=Label(text,12),BorderBrush=Brush("#DCE3EA"),BorderThickness=new Thickness(.5),Padding=new Thickness(5,2,5,2),Background=Brushes.White});
        var footer=new DockPanel{Margin=new Thickness(0,7,0,0)};var copy=new Button{Content="复制",Padding=new Thickness(8,4,8,4),HorizontalAlignment=HorizontalAlignment.Left};
        copy.Click+=(_,_)=>{try{Clipboard.SetText(OpportunityModel.CopyStrategy(data)??string.Join('\n',VisibleText(stack))+"\n"+OpportunityModel.Radar(data));copy.Content="已复制";}catch{copy.Content="复制失败，请重试";}};
        SetDock(copy,Dock.Left);footer.Children.Add(copy);
        if(OpportunityModel.Radar(data) is {} url){var button=new Button{Content="雷达 ↗",Padding=new Thickness(8,4,8,4),HorizontalAlignment=HorizontalAlignment.Right};button.Click+=(_,_)=>MessageText.Open(url);footer.Children.Add(button);}stack.Children.Add(footer);
        var result=Box(stack,level>=10?"#FFF2F2":level>=6?"#FFF6EE":level>=4?"#FFFCED":level>=2?"#F1F7FF":"#F8FAFB");
        result.ToolTip=$"进入：{OpportunityModel.Date(data,"enteredAt").ToOffset(TimeSpan.FromHours(8)):yyyy-MM-dd HH:mm:ss} UTC+8\n更新：{OpportunityModel.Date(data,"updatedAt").ToOffset(TimeSpan.FromHours(8)):HH:mm:ss} UTC+8";return result;
    }
    private static string Exchange(JsonElement leg)=>OpportunityModel.Text(leg,"exchange")=="hyperliquid"?"HL":OpportunityModel.Text(leg,"exchange").ToUpperInvariant();
    private static IEnumerable<string> VisibleText(DependencyObject parent)
    {
        if(parent is TextBlock block){yield return block.Text;yield break;}
        for(var i=0;i<VisualTreeHelper.GetChildrenCount(parent);i++)foreach(var text in VisibleText(VisualTreeHelper.GetChild(parent,i)))yield return text;
    }
    internal static string[] Transfers(JsonElement[] legs,JsonElement[] wallets,DateTimeOffset now)
    {
        var rows=new List<string>();
        foreach(var leg in legs)
        {
            var symbol=OpportunityModel.Text(leg,"symbol").ToUpperInvariant();var match=Regex.Match(symbol,@"^([\p{L}\p{N}_]{1,40})(?:/|_)?USDT$");var coin=match.Success?match.Groups[1].Value.TrimEnd('_'):"";
            var wallet=wallets.FirstOrDefault(w=>OpportunityModel.Text(w,"key")==OpportunityModel.Text(leg,"exchange")+":"+coin);var text=OpportunityModel.Text(wallet,"text");var checkedAt=OpportunityModel.Date(wallet,"checkedAt");var expires=OpportunityModel.Date(wallet,"expiresAt");
            var valid=coin.Length>0&&OpportunityModel.Get(wallet,"refreshFailed").ValueKind==JsonValueKind.False&&checkedAt<=now.AddSeconds(30)&&checkedAt!=DateTimeOffset.MinValue&&expires>now;
            var noSpot=valid&&!OpportunityModel.True(leg,"spot")&&expires-checkedAt<=TimeSpan.FromMilliseconds(7200001)&&Regex.IsMatch(text,"[｜|]无现货[｜|】]")&&text.Contains("该平台无现货",StringComparison.Ordinal);
            if(noSpot){rows.Add(Exchange(leg)+"   — / —  无现货");continue;}
            if(!valid||now-checkedAt>TimeSpan.FromMinutes(2)||!Regex.IsMatch(text,"【(?:官方|官方名单|Cexorer补充)[｜|]")){rows.Add(Exchange(leg)+"   ? / ?  未知");continue;}
            var body=text.Split("】：",2);var clauses=new List<string>();
            if(body.Length==2)foreach(var clause in Regex.Split(body[1],"[；;\\n]"))
            {
                var m=Regex.Match(clause,@"^\s*充(开|关|支持|延迟|拥堵|受限|未知|\?)/提(开|关|支持|延迟|拥堵|受限|未知|\?)\s+([^：:；;]+)\s*$");
                if(m.Success){string Status(string s)=>s switch{"开"=>"✓","关"=>"×","未知"=>"?",_=>s};clauses.Add(m.Groups[3].Value.Trim()+"   "+Status(m.Groups[1].Value)+" / "+Status(m.Groups[2].Value));}
            }
            rows.Add(Exchange(leg)+"   "+(clauses.Count>0?string.Join("；",clauses):"? / ?  未知"));
        }
        return rows.ToArray();
    }
}
