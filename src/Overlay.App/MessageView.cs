using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Media;
using Overlay.Core;
namespace Overlay.App;

// Constructed only for the four displayed messages or finite fit measurements.
// No media fetch, scripting, timers, or automatic link navigation.
public sealed class MessageView : Grid
{
    public static readonly DependencyProperty MessageProperty=DependencyProperty.Register(nameof(Message),typeof(IncomingMessage),typeof(MessageView),new PropertyMetadata(null,(o,e)=>((MessageView)o).Rebuild()));
    public IncomingMessage? Message {get=>(IncomingMessage?)GetValue(MessageProperty);set=>SetValue(MessageProperty,value);}
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
    private void Rebuild()
    {
        Children.Clear();ColumnDefinitions.Clear();RowDefinitions.Clear();if(Message is not {} message)return;
        var outer=new Border{BorderBrush=new SolidColorBrush(Color.FromRgb(216,216,216)),BorderThickness=new Thickness(0,0,0,.5),Padding=new Thickness(1,1,1,3)};Children.Add(outer);
        var card=message.Card;
        if(card is null)
        {
            var row=new Grid();row.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});row.ColumnDefinitions.Add(new(){Width=GridLength.Auto});
            var body=Block(message.Text,2);body.Margin=new Thickness(0,0,3,0);row.Children.Add(body);var clock=Clock(message);SetColumn(clock,1);row.Children.Add(clock);outer.Child=row;return;
        }
        var stack=new StackPanel();outer.Child=stack;
        if(card.Title.Length>0)
        {
            var color=Tone(card.HeaderTone);var light=Color.FromRgb((byte)Math.Min(255,color.R+18),(byte)Math.Min(255,color.G+18),(byte)Math.Min(255,color.B+18));
            var header=new Border{Background=new LinearGradientBrush(color,light,0),CornerRadius=new CornerRadius(2),Padding=new Thickness(5,3,4,3),Margin=new Thickness(0,0,0,3)};
            var row=new Grid();row.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});row.ColumnDefinitions.Add(new(){Width=GridLength.Auto});
            var title=new TextBlock{Text=card.Title,Foreground=Brushes.White,FontWeight=FontWeights.Bold,TextWrapping=TextWrapping.Wrap};row.Children.Add(title);var clock=Clock(message);clock.Foreground=Brushes.White;SetColumn(clock,1);row.Children.Add(clock);header.Child=row;stack.Children.Add(header);
        }
        else {var clock=Clock(message);clock.HorizontalAlignment=HorizontalAlignment.Right;stack.Children.Add(clock);}
        if(card.Body.Length>0)stack.Children.Add(Block(card.Body,markdown:card.IsMarkdown));
        if(card.Buttons.Count>0)
        {
            var buttons=new WrapPanel{Margin=new Thickness(0,3,0,0)};
            foreach(var action in card.Buttons)
            {
                var button=new Button{Content=action.Label,Tag=action.Url,Style=Application.Current.MainWindow?.TryFindResource("CardButton") as Style,IsEnabled=MessageCardParser.SafeUrl(action.Url),ToolTip=action.Url.Length>0?action.Url:"当前消息未获得可打开的HTTP(S)地址",Margin=new Thickness(0,0,4,0)};
                button.Click+=(_,e)=>{if(button.Tag is string url && MessageCardParser.SafeUrl(url))MessageText.Open(url);e.Handled=true;};buttons.Children.Add(button);
            }
            stack.Children.Add(buttons);
        }
    }
}
