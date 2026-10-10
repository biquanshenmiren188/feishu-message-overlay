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
    internal static string? CopyGcStrategy(JsonElement data)
    {
        var legs=Array(Get(data,"details"),"legs",3);
        var supported=new[]{"binance","bybit","gate","hyperliquid"};
        if(Text(data,"strategy")!="FF"||legs.Length!=2||legs.Any(l=>Get(l,"spot").ValueKind!=JsonValueKind.False||!supported.Contains(Text(l,"exchange"))))return null;
        var normal=CopyStrategy(data);if(normal is null)return null;
        var payload=JsonSerializer.Deserialize<Dictionary<string,string>>(normal[(normal.IndexOf('\n')+1)..])!;
        payload["buyEx"]="gc-"+payload["buyEx"];payload["sellEx"]="gc-"+payload["sellEx"];
        return "ASTRO-QUICK-COPY:\n"+JsonSerializer.Serialize(payload,new JsonSerializerOptions{WriteIndented=true}).Replace("\r\n","\n",StringComparison.Ordinal);
    }
    internal static string? CopyStrategy(JsonElement data)
    {
        var legs=Array(Get(data,"details"),"legs",3);var strategy=Text(data,"strategy");
        if(legs.Length!=2||strategy is not ("SF" or "FS" or "FF"))return null;
        var allowed=new[]{"binance","bitget","bybit","gate","okx","aster","hyperliquid"};
        var buy=Text(legs[0],"exchange");var sell=Text(legs[1],"exchange");
        if(!allowed.Contains(buy)||!allowed.Contains(sell)||strategy=="FS"&&sell is "aster" or "hyperliquid")return null;
        if(True(legs[0],"spot")!=(strategy=="SF")||True(legs[1],"spot")!=(strategy=="FS"))return null;
        string Symbol(JsonElement leg){var s=Text(leg,"symbol").ToUpperInvariant();if(Text(leg,"exchange")=="okx"&&!True(leg,"spot")&&Regex.IsMatch(s,"^[A-Z0-9]+-USDT-SWAP$"))s=s[..^5];s=Regex.Replace(s,"[_/\\-]","");if(Text(leg,"exchange")=="hyperliquid"&&!True(leg,"spot")&&Regex.IsMatch(s,"^[A-Z0-9]+$")&&!s.EndsWith("USDT",StringComparison.Ordinal))s+="USDT";return s;}
        var a=Symbol(legs[0]);if(a!=Symbol(legs[1])||!Regex.IsMatch(a,"^[A-Z0-9]+USDT$"))return null;
        var payload=new Dictionary<string,string>{{"type",strategy},{"name",a[..^4]},{"buyEx",buy=="hyperliquid"?"hl":buy},{"sellEx",sell=="hyperliquid"?"hl":sell}};
        if(strategy=="FS")payload["spotMarginType"]="cross";
        return "ASTRO-QUICK-COPY:\n"+JsonSerializer.Serialize(payload,new JsonSerializerOptions{WriteIndented=true}).Replace("\r\n","\n",StringComparison.Ordinal);
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
        heading.Visibility=Visibility.Collapsed;Margin=new Thickness(0);LastChildFill=true;SetDock(heading,Dock.Top);Children.Add(heading);
        ScrollViewer.SetHorizontalScrollBarVisibility(cards,ScrollBarVisibility.Disabled);
        ScrollViewer.SetVerticalScrollBarVisibility(cards,ScrollBarVisibility.Hidden);
        ScrollViewer.SetCanContentScroll(cards,true);VirtualizingPanel.SetIsVirtualizing(cards,true);VirtualizingPanel.SetVirtualizationMode(cards,VirtualizationMode.Recycling);
        var factory=new FrameworkElementFactory(typeof(OpportunityPresenter));cards.ItemTemplate=new DataTemplate{VisualTree=factory};
        cards.Padding=new Thickness(0);
        // The default ListBox template adds a one-pixel ScrollViewer margin.
        var viewport=new FrameworkElementFactory(typeof(ScrollViewer));viewport.SetValue(ScrollViewer.CanContentScrollProperty,true);viewport.SetValue(ScrollViewer.VerticalScrollBarVisibilityProperty,ScrollBarVisibility.Hidden);viewport.SetValue(ScrollViewer.HorizontalScrollBarVisibilityProperty,ScrollBarVisibility.Disabled);viewport.SetValue(Control.PaddingProperty,new Thickness(0));viewport.SetValue(FrameworkElement.MarginProperty,new Thickness(0));viewport.AppendChild(new FrameworkElementFactory(typeof(ItemsPresenter)));cards.Template=new ControlTemplate(typeof(ListBox)){VisualTree=viewport};
        var style=new Style(typeof(ListBoxItem));style.Setters.Add(new Setter(Control.HorizontalContentAlignmentProperty,HorizontalAlignment.Stretch));style.Setters.Add(new Setter(Control.PaddingProperty,new Thickness(0)));style.Setters.Add(new Setter(FrameworkElement.MarginProperty,new Thickness(0)));style.Setters.Add(new Setter(Control.BorderThicknessProperty,new Thickness(0)));style.Setters.Add(new Setter(Control.FocusableProperty,false));style.Setters.Add(new Setter(FrameworkElement.FocusVisualStyleProperty,null));
        var presenter=new FrameworkElementFactory(typeof(ContentPresenter));
        style.Setters.Add(new Setter(Control.TemplateProperty,new ControlTemplate(typeof(ListBoxItem)){VisualTree=presenter}));cards.ItemContainerStyle=style;
        Children.Add(cards);
    }
    private static Brush Brush(string hex)=>new SolidColorBrush((Color)ColorConverter.ConvertFromString(hex));
    private static TextBlock Label(string text,double size=12,bool bold=false,string color="#263238")=>new(){Text=text,TextWrapping=TextWrapping.Wrap,FontSize=size,FontWeight=bold?FontWeights.SemiBold:FontWeights.Normal,Foreground=Brush(color),Margin=new Thickness(1,1,1,1)};
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
        cards.ItemsSource=ordered.Length>0?ordered.Select(entry=>(object)new OpportunityItem(this,entry,now)).ToArray():System.Array.Empty<object>();
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
        var rank=level>=10?"#E3444E":level>=6?"#E47C23":level>=4?"#C49500":level>=2?"#4085DF":"#8B95A5";
        var rankText=level>=10?"#B72136":level>=6?"#9C490C":level>=4?"#866400":level>=2?"#245B9E":"#596271";
        var stack=new StackPanel();
        var age=Math.Max(0,(int)(now-OpportunityModel.Date(data,"enteredAt")).TotalSeconds);
        var title=new Grid{Margin=new Thickness(0,0,0,3)};title.ColumnDefinitions.Add(new());title.ColumnDefinitions.Add(new(){Width=GridLength.Auto});title.ColumnDefinitions.Add(new(){Width=GridLength.Auto});
        var name=Label("",13,true);name.Inlines.Add(new System.Windows.Documents.Run(OpportunityModel.Asset(data)));var strategyBadge=new Border{Child=Label(OpportunityModel.Text(data,"strategy"),8,color:"#476371"),Background=Brush("#E9EDEB"),Margin=new Thickness(3,0,0,0),Padding=new Thickness(1),VerticalAlignment=VerticalAlignment.Center};name.Inlines.Add(new System.Windows.Documents.InlineUIContainer(strategyBadge){BaselineAlignment=BaselineAlignment.Center});title.Children.Add(name);
        var status=Label((state=="ACTIVE"?"● ACTIVE "+age+"s":state)+" · "+(OpportunityModel.Text(data,"trigger")=="v2_price_window"?"V2收敛":OpportunityModel.Text(data,"trigger")),8,true,state=="ACTIVE"?"#28765B":"#A16910");status.VerticalAlignment=VerticalAlignment.Center;status.Margin=new Thickness(3,0,4,0);Grid.SetColumn(status,1);title.Children.Add(status);
        var badge=new Border{Child=Label($"R{(level?.ToString(CultureInfo.InvariantCulture)??"—")} {OpportunityModel.Percent(OpportunityModel.Number(residual,"bps"))}",10,true,rankText),Background=Brush("#F7F9FB"),BorderBrush=Brush(rankText),BorderThickness=new Thickness(.7),CornerRadius=new CornerRadius(4),Padding=new Thickness(3,1,3,1)};Grid.SetColumn(badge,2);title.Children.Add(badge);stack.Children.Add(title);
        var legs=OpportunityModel.Array(detail,"legs",2);var legGrid=new Grid{Margin=new Thickness(0,0,0,4),MinHeight=44};legGrid.ColumnDefinitions.Add(new());legGrid.ColumnDefinitions.Add(new());
        for(var i=0;i<legs.Length;i++)
        {
            var leg=legs[i];var spot=OpportunityModel.True(leg,"spot");var panel=new Grid{Margin=new Thickness(i==0?0:5,0,i==0?5:0,0)};panel.ColumnDefinitions.Add(new());panel.ColumnDefinitions.Add(new(){Width=GridLength.Auto});
            var main=new StackPanel();main.Children.Add(Label((i==0?"买 ":"卖 ")+Exchange(leg)+(spot?" 现货":" 永续"),11,true));
            if(!spot){var rate=new StackPanel{Orientation=Orientation.Horizontal};var number=Label(OpportunityModel.Percent(OpportunityModel.Number(leg,"rate"),.01),15,true);number.FontFamily=new FontFamily("Consolas");rate.Children.Add(number);var hours=OpportunityModel.Number(leg,"hours");var cycle=hours==1?("#9A3900","#FFF0E1","#D06A15"):hours==8?("#155CAD","#E7F1FF","#4383C5"):hours is >0?("#7031A7","#F1E8FF","#9A62C8"):("#657B89","#00FFFFFF","#DCE3E8");rate.Children.Add(new Border{Child=Label(OpportunityModel.Number(leg,"hours") is {} h?$"{h}h":"—",11,color:cycle.Item1),BorderBrush=Brush(cycle.Item3),BorderThickness=new Thickness(.7),CornerRadius=new CornerRadius(2),Background=Brush(cycle.Item2),Padding=new Thickness(2,0,2,0),Margin=new Thickness(3,2,0,2),VerticalAlignment=VerticalAlignment.Center});main.Children.Add(rate);}panel.Children.Add(main);
            var stats=new StackPanel{Margin=new Thickness(2,1,0,0)};
            foreach(var metric in spot?new[]{("24H","volume")}:new[]{("24H","volume"),("OI","oi")}){var caption=Label(metric.Item1,8,color:"#747570");caption.TextAlignment=TextAlignment.Right;caption.Margin=new Thickness(0);stats.Children.Add(caption);var value=Label(OpportunityModel.Money(OpportunityModel.Number(leg,metric.Item2)),9);value.FontFamily=new FontFamily("Consolas");value.TextAlignment=TextAlignment.Right;value.Margin=new Thickness(0);stats.Children.Add(value);}Grid.SetColumn(stats,1);panel.Children.Add(stats);Grid.SetColumn(panel,i);legGrid.Children.Add(panel);
        }stack.Children.Add(legGrid);
        var metrics=new Grid{Margin=new Thickness(0,0,0,4)};for(var i=0;i<4;i++)metrics.ColumnDefinitions.Add(new());
        var names=new[]{"净收益均值","盘口差均值","盘口差 P75","指数差均值"};var keys=new[]{"netBps","marketBps","p75Bps","indexBps"};
        for(var i=0;i<4;i++){var column=new StackPanel();var caption=Label(names[i],10,color:"#536977");caption.TextAlignment=TextAlignment.Center;column.Children.Add(caption);var text=OpportunityModel.Percent(OpportunityModel.Number(detail,keys[i]));var value=Label(i==0?text.TrimStart('+'):text,12,true);value.TextAlignment=TextAlignment.Center;value.FontFamily=new FontFamily("Consolas");column.Children.Add(value);var cell=new Border{Child=column,BorderBrush=Brush("#DCE3EA"),BorderThickness=new Thickness(.4),Background=Brushes.White,Padding=new Thickness(1,2,1,2)};Grid.SetColumn(cell,i);metrics.Children.Add(cell);}stack.Children.Add(metrics);
        var warnings=new List<string>();foreach(var news in OpportunityModel.Array(detail,"newsWarnings",20)){var text=OpportunityModel.Text(news,"summary");if(text.Length>0)warnings.Add(OpportunityModel.Text(news,"exchange").ToUpperInvariant()+" "+text+(OpportunityModel.Text(news,"status")=="postponed"?"（已延期，时间未定）":OpportunityModel.Text(news,"status")=="uncertain"?"（待确认）":""));}
        if(legs.Length==2&&!OpportunityModel.True(legs[0],"spot")&&!OpportunityModel.True(legs[1],"spot")&&OpportunityModel.Number(legs[0],"hours") is >0 and var h0&&OpportunityModel.Number(legs[1],"hours") is >0 and var h1&&h0!=h1)warnings.Add($"周期 {h0}h/{h1}h");
        if(legs.Any(l=>OpportunityModel.Text(l,"exchange")=="bybit"&&!OpportunityModel.True(l,"spot")&&OpportunityModel.Number(l,"hours")==1))warnings.Add("Bybit 1h 计算不同");
        if(warnings.Count>0)stack.Children.Add(new Border{Child=Label("⚠ "+string.Join(" · ",warnings),10,true,"#BA2948"),Background=Brush("#FFF0F4"),Padding=new Thickness(5,1,5,1),Margin=new Thickness(0,0,0,4),BorderBrush=Brush("#E0294A"),BorderThickness=new Thickness(2,0,0,0)});
        var transferHeading=new StackPanel{Orientation=Orientation.Horizontal};transferHeading.Children.Add(Label("现货充提",12,true,"#476371"));transferHeading.Children.Add(Label(" 充 / 提 · ✓开 ×关 ?未知 —无数据",8,color:"#647E8D"));stack.Children.Add(transferHeading);
        var transfers=Transfers(legs,OpportunityModel.Array(detail,"transferWallets",20),now);
        var rows=transfers.Select(t=>t.Split("   ",2)).ToArray();var chains=rows.SelectMany(r=>r.Length<2?[]:r[1].Split('；').Select(c=>c.Split("   ",2)).Where(c=>c.Length==2).Select(c=>c[0])).Distinct().ToArray();if(chains.Length==0)chains=["状态"];
        var table=new Grid{Margin=new Thickness(0,0,0,4)};table.ColumnDefinitions.Add(new(){Width=new GridLength(66)});foreach(var chain in chains)table.ColumnDefinitions.Add(new());for(var i=0;i<=rows.Length;i++)table.RowDefinitions.Add(new(){Height=GridLength.Auto});
        void Cell(UIElement child,int row,int col){var box=new Border{Child=child,BorderBrush=Brush("#DCE3EA"),BorderThickness=new Thickness(.4),Padding=new Thickness(2,1,2,1),Background=Brush(row==0?"#F5F7F9":"#FDFEFE"),MinHeight=18};Grid.SetRow(box,row);Grid.SetColumn(box,col);table.Children.Add(box);}
        TextBlock Center(string text,bool bold=false,string color="#263238"){var t=Label(text,9,bold,color);t.TextAlignment=TextAlignment.Center;t.Margin=new Thickness(0,1,0,1);return t;}
        Cell(Center("链",false,"#536977"),0,0);for(var j=0;j<chains.Length;j++)Cell(Center(chains[j],false,"#536977"),0,j+1);
        for(var i=0;i<rows.Length;i++){Cell(Center(rows[i][0],true),i+1,0);var body=rows[i].ElementAtOrDefault(1)??"";for(var j=0;j<chains.Length;j++){var clause=body.Split('；').FirstOrDefault(c=>c.StartsWith(chains[j]+"   ",StringComparison.Ordinal));var statusText=clause is not null?clause.Split("   ",2)[1]:body.Contains("无现货",StringComparison.Ordinal)?"— / —":"? / ?";var pair=statusText.Split('/');var pairGrid=new Grid();pairGrid.ColumnDefinitions.Add(new());pairGrid.ColumnDefinitions.Add(new());for(var k=0;k<2;k++){var token=(pair.ElementAtOrDefault(k)??"?").Trim().Split(' ')[0];var label=Center(token,true,token=="?"?"#896925":token=="✓"?"#286E72":"#5E6664");Grid.SetColumn(label,k);pairGrid.Children.Add(label);}Cell(pairGrid,i+1,j+1);}}stack.Children.Add(table);
        Button FooterButton(string text)=>new(){Content=text,Padding=new Thickness(7,2,7,2),Margin=new Thickness(0,0,6,6),FontSize=10,MinHeight=20,Height=20,VerticalAlignment=VerticalAlignment.Top,Background=Brushes.White,BorderBrush=Brush("#DCE3EA"),HorizontalAlignment=HorizontalAlignment.Left};
        var footer=new DockPanel{Margin=new Thickness(0,2,0,0)};var copy=FooterButton("复制");
        copy.Click+=(_,_)=>{try{Clipboard.SetText(OpportunityModel.CopyStrategy(data)??string.Join('\n',VisibleText(stack))+"\n"+OpportunityModel.Radar(data));copy.Content="已复制";}catch{copy.Content="复制失败，请重试";}};
        SetDock(copy,Dock.Left);footer.Children.Add(copy);
        if(OpportunityModel.CopyGcStrategy(data) is {} gcPayload){var gc=FooterButton("复制 GC");gc.ToolTip="复制 Gate Crossex 代码";gc.Click+=(_,_)=>{try{Clipboard.SetText(gcPayload);gc.Content="GC 已复制";}catch{gc.Content="复制失败";}};SetDock(gc,Dock.Left);footer.Children.Add(gc);}
        if(OpportunityModel.Radar(data) is {} url){var button=FooterButton("雷达 ↗");button.HorizontalAlignment=HorizontalAlignment.Right;button.Click+=(_,_)=>MessageText.Open(url);footer.Children.Add(button);}stack.Children.Add(footer);
        var rankColor=(Color)ColorConverter.ConvertFromString(rank);
        byte Wash(byte channel)=>(byte)Math.Round(channel*.04+255*.96);
        var result=Box(stack);result.Background=new SolidColorBrush(Color.FromRgb(Wash(rankColor.R),Wash(rankColor.G),Wash(rankColor.B)));
        result.Margin=new Thickness(0);result.CornerRadius=new CornerRadius(0);result.Padding=new Thickness(6,4,6,4);result.BorderBrush=Brush(rank);result.BorderThickness=new Thickness(.7);
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
