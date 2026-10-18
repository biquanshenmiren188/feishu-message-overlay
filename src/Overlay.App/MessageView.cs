using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Media;
using System.Windows.Input;
using System.Windows.Controls.Primitives;
using System.Windows.Documents;
using System.Windows.Automation;
using Overlay.Core;
namespace Overlay.App;

// The retained history is bounded by MessageStore; display never changes source data.
// No media fetch, scripting, timers, or automatic link navigation.
public sealed class MessageView : Grid
{
    public static readonly DependencyProperty MessageProperty=DependencyProperty.Register(nameof(Message),typeof(IncomingMessage),typeof(MessageView),new PropertyMetadata(null,(o,e)=>((MessageView)o).Rebuild()));
    public IncomingMessage? Message {get=>(IncomingMessage?)GetValue(MessageProperty);set=>SetValue(MessageProperty,value);}
    internal TextBlock? FullBody {get;private set;}
    internal bool IsExpanded=>FullBody?.Visibility==Visibility.Visible;
    private static bool IsAction(DependencyObject? source,DependencyObject boundary)
    {
        while(source is not null && source!=boundary)
        {
            if(source is ButtonBase or Hyperlink)return true;
            source=source is FrameworkContentElement content?content.Parent:VisualTreeHelper.GetParent(source);
        }
        return false;
    }
    internal void ToggleFullBody()
    {
        if(FullBody is null)return;
        FullBody.Visibility=IsExpanded?Visibility.Collapsed:Visibility.Visible;
        AutomationProperties.SetHelpText(this,IsExpanded?"已展开，点击消息或按回车收起原文":"点击消息或按回车展开原文");
    }
    private static Button ActionButton(CardLink action)
    {
        var button=new Button{Content=action.Label,Tag=action.Url,Style=Application.Current.MainWindow?.TryFindResource("CardButton") as Style,IsEnabled=MessageCardParser.SafeUrl(action.Url),ToolTip=action.Url.Length>0?action.Url:"当前消息未获得可打开的HTTP(S)地址",Margin=new Thickness(0,0,4,0)};
        button.Click+=(_,e)=>{if(button.Tag is string url && MessageCardParser.SafeUrl(url))MessageText.Open(url);e.Handled=true;};
        return button;
    }
    private TextBlock Block(string text,int bold=0,bool markdown=false)
    {
        var block=new TextBlock{TextWrapping=TextWrapping.Wrap,Foreground=Brushes.Black};
        MessageText.SetBoldLines(block,bold);MessageText.SetMarkdown(block,markdown);MessageText.SetContent(block,text);
        block.SetBinding(TextBlock.LineHeightProperty,new Binding("(TextElement.FontSize)"){Source=this,Converter=new BodyLineHeight()});return block;
    }
    private TextBlock Clock(IncomingMessage message)
    {
        var block=new TextBlock{Text=(string)new MessageTime().Convert(message.SentAt,typeof(string),null!,System.Globalization.CultureInfo.InvariantCulture),ToolTip=new MessageTime().Convert(message.SentAt,typeof(string),"date",System.Globalization.CultureInfo.InvariantCulture),Foreground=new SolidColorBrush(Color.FromRgb(112,112,112)),FontWeight=FontWeights.SemiBold,Margin=new Thickness(3,1,0,0),VerticalAlignment=VerticalAlignment.Top};
        block.SetBinding(TextBlock.FontSizeProperty,new Binding("(TextElement.FontSize)"){Source=this,Converter=new TimeFontScale()});return block;
    }
    private static Color Tone(string name)=>name switch
    {"blue"=>Color.FromRgb(62,105,184),"green"=>Color.FromRgb(54,132,91),"red"=>Color.FromRgb(184,73,75),"orange"=>Color.FromRgb(179,112,39),"purple"=>Color.FromRgb(130,86,165),"indigo"=>Color.FromRgb(91,94,174),"turquoise"=>Color.FromRgb(43,129,132),"yellow"=>Color.FromRgb(153,125,44),_=>Color.FromRgb(135,141,151)};
    internal static string RankFirstTitle(string title)
    {
        var parts=title.Split(new[]{'｜','|'}).Select(part=>part.Trim()).ToArray();
        var index=Array.FindIndex(parts,part=>System.Text.RegularExpressions.Regex.IsMatch(part,@"^R\d+\+?\s+[+−-]?\d+(?:\.\d+)?\s*%$",System.Text.RegularExpressions.RegexOptions.IgnoreCase));
        return index<=0?title:string.Join("｜",new[]{parts[index]}.Concat(parts.Where((_,i)=>i!=index)));
    }
    private void Rebuild()
    {
        FullBody=null;Children.Clear();ColumnDefinitions.Clear();RowDefinitions.Clear();if(Message is not {} message)return;
        var outer=new Border{BorderBrush=new SolidColorBrush(Color.FromRgb(216,216,216)),BorderThickness=new Thickness(0,0,0,.5),Padding=new Thickness(1,1,1,3)};Children.Add(outer);
        var card=message.Card;
        var summary=CompactMessage.From(card?.Title,card?.Body??message.Text);
        var compact=summary.Body.Length>0||System.Text.RegularExpressions.Regex.IsMatch(summary.Title,@"[｜|]\s*(FF|SF|FS)\s*[｜|]");
        if(compact&&card is null)card=new MessageCard("",message.Text,Array.Empty<CardLink>());
        if(card is null)
        {
            var row=new Grid();row.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});row.ColumnDefinitions.Add(new(){Width=GridLength.Auto});
            var body=Block(message.Text,2);body.Margin=new Thickness(0,0,3,0);row.Children.Add(body);var clock=Clock(message);SetColumn(clock,1);row.Children.Add(clock);outer.Child=row;return;
        }
        var stack=new StackPanel();outer.Child=stack;
        var displayTitle=RankFirstTitle(compact?summary.Title:card.Title);
        if(displayTitle.Length>0)
        {
            var color=Tone(MessageCard.SafeTone(card.HeaderTone));var light=Color.FromRgb((byte)(255-(255-color.R)*.12),(byte)(255-(255-color.G)*.12),(byte)(255-(255-color.B)*.12));
            var header=new Border{Background=new SolidColorBrush(light),CornerRadius=new CornerRadius(2),Padding=new Thickness(5,3,4,3),Margin=new Thickness(0,0,0,3)};
            var row=new Grid();row.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});row.ColumnDefinitions.Add(new(){Width=GridLength.Auto});
            var titleColor=MessageCard.SafeTone(card.HeaderTone)=="grey"?Color.FromRgb(17,17,17):color;
            var title=new TextBlock{Text=displayTitle,Foreground=new SolidColorBrush(titleColor),FontWeight=FontWeights.ExtraBold,TextWrapping=TextWrapping.Wrap};row.Children.Add(title);var clock=Clock(message);clock.Foreground=new SolidColorBrush(Color.FromRgb(112,112,112));SetColumn(clock,1);row.Children.Add(clock);header.Child=row;stack.Children.Add(header);
        }
        else {var clock=Clock(message);clock.HorizontalAlignment=HorizontalAlignment.Right;stack.Children.Add(clock);}
        if(compact)
        {
            if(summary.Spread.Length>0)
            {
                var spread=new Grid{VerticalAlignment=VerticalAlignment.Center};
                spread.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});spread.ColumnDefinitions.Add(new(){Width=GridLength.Auto});
                var text=Block(summary.Spread);text.VerticalAlignment=VerticalAlignment.Center;text.Margin=new Thickness(0,0,8,0);spread.Children.Add(text);
                var inlineActions=new WrapPanel{HorizontalAlignment=HorizontalAlignment.Right,VerticalAlignment=VerticalAlignment.Center};SetColumn(inlineActions,1);spread.Children.Add(inlineActions);
                foreach(var action in card.Buttons.Where(a=>a.Label=="查看雷达")){var button=ActionButton(action);button.Margin=new Thickness(4,0,0,0);inlineActions.Children.Add(button);}
                stack.Children.Add(spread);
            }
            if(summary.Signals.Length>0)stack.Children.Add(Block(summary.Signals));
            if(summary.Warning){var warning=Block(summary.Risk);warning.Foreground=new SolidColorBrush(Color.FromRgb(163,62,37));stack.Children.Add(warning);}
            if(card.Body.Length>0)
            {
                FullBody=Block(card.Body,markdown:card.IsMarkdown);FullBody.Visibility=Visibility.Collapsed;FullBody.Margin=new Thickness(0,6,0,3);stack.Children.Add(FullBody);
                outer.Focusable=true;outer.Background=Brushes.Transparent;outer.ToolTip="点击消息展开或收起原文";
                AutomationProperties.SetName(outer,displayTitle);AutomationProperties.SetHelpText(outer,"点击或按回车展开、收起原文");
                outer.MouseLeftButtonUp+=(_,e)=>{if(IsAction(e.OriginalSource as DependencyObject,outer))return;outer.Focus();ToggleFullBody();e.Handled=true;};
                outer.KeyDown+=(_,e)=>{if(e.OriginalSource==outer && e.Key is Key.Enter or Key.Space){ToggleFullBody();e.Handled=true;}};
            }
        }
        else if(card.Body.Length>0)stack.Children.Add(Block(card.Body,markdown:card.IsMarkdown));
        if(card.Buttons.Count>0)
        {
            var buttons=new WrapPanel{Margin=new Thickness(0,3,0,0),HorizontalAlignment=HorizontalAlignment.Right};
            foreach(var action in card.Buttons.Where(a=>!(compact && summary.Spread.Length>0 && a.Label=="查看雷达")))
            {
                var button=ActionButton(action);button.Margin=new Thickness(4,0,0,0);buttons.Children.Add(button);
            }
            if(buttons.Children.Count>0)stack.Children.Add(buttons);
        }
    }
}
