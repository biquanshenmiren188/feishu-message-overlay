using System.Diagnostics;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
namespace Overlay.App;
public static partial class MessageText
{
    public static readonly DependencyProperty ContentProperty = DependencyProperty.RegisterAttached("Content", typeof(string), typeof(MessageText), new PropertyMetadata("", Changed));
    public static string GetContent(DependencyObject obj) => (string)obj.GetValue(ContentProperty);
    public static void SetContent(DependencyObject obj, string value) => obj.SetValue(ContentProperty, value);
    public static readonly DependencyProperty BoldLinesProperty=DependencyProperty.RegisterAttached("BoldLines",typeof(int),typeof(MessageText),new PropertyMetadata(2));
    public static void SetBoldLines(DependencyObject o,int value)=>o.SetValue(BoldLinesProperty,value);
    public static int GetBoldLines(DependencyObject o)=>(int)o.GetValue(BoldLinesProperty);
    [GeneratedRegex(@"https?://[^\s<>""\u3000，。；！？、（）【】《》「」『』]+", RegexOptions.IgnoreCase)]
    private static partial Regex Links();
    internal static Action<Uri> Launch = uri => Process.Start(new ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute = true });
    internal static bool Open(string text)
    {
        if (!Uri.TryCreate(text, UriKind.Absolute, out var uri) || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps)) return false;
        try { Launch(uri); return true; } catch (Exception) { return false; }
    }
    private static void Changed(DependencyObject obj, DependencyPropertyChangedEventArgs args)
    {
        if (obj is not TextBlock block) return;
        var text = args.NewValue as string ?? "";
        var boldLimit=text.Length;var lines=0;
        for(var i=0;i<text.Length;i++)
        {
            if(text[i] is not ('\r' or '\n'))continue;
            if(text[i]=='\r' && i+1<text.Length && text[i+1]=='\n')i++;
            if(++lines==GetBoldLines(block)){boldLimit=i+1;break;}
        }
        block.Inlines.Clear(); var offset = 0;
        void Plain(int start,int end)
        {
            var split=Math.Clamp(boldLimit,start,end);
            if(split>start)block.Inlines.Add(new Run(text[start..split]){FontWeight=FontWeights.Bold});
            if(end>split)block.Inlines.Add(new Run(text[split..end]){FontWeight=FontWeights.Normal});
        }
        foreach (Match match in Links().Matches(text))
        {
            if (match.Index > offset) Plain(offset,match.Index);
            var address=match.Value;
            if(!address.Contains('?'))address=address.TrimEnd('.',',','!');
            while(address.EndsWith(')') && address.Count(c=>c==')')>address.Count(c=>c=='('))address=address[..^1];
            var link = new Hyperlink(new Run(address)) { Foreground = new SolidColorBrush(Color.FromRgb(0,95,184)), ToolTip = address };
            link.FontWeight=match.Index<boldLimit?FontWeights.Bold:FontWeights.Normal;
            // Never launch during parsing/binding. Only an explicit click opens HTTP(S).
            link.Click += (_, e) => { Open(address); e.Handled = true; };
            block.Inlines.Add(link); offset = match.Index + address.Length;
        }
        if (offset < text.Length) Plain(offset,text.Length);
    }
}
