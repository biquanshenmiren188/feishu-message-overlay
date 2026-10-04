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
    public static readonly DependencyProperty MarkdownProperty=DependencyProperty.RegisterAttached("Markdown",typeof(bool),typeof(MessageText),new PropertyMetadata(false));
    public static void SetMarkdown(DependencyObject o,bool value)=>o.SetValue(MarkdownProperty,value);
    public static bool GetMarkdown(DependencyObject o)=>(bool)o.GetValue(MarkdownProperty);
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
        if(GetMarkdown(block)){RenderMarkdown(block,text);return;}
        var boldLimit=GetBoldLines(block)<=0?0:text.Length;var lines=0;
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
    // A small literal renderer, not HTML/XAML/script execution. Unknown markup stays text.
    private static void RenderMarkdown(TextBlock block,string text)
    {
        block.Inlines.Clear();var offset=0;var scan=0;var attempts=0;
        void Plain(string value,bool bold=false)
        {
            if(value.Length==0)return;
            var temporary=new TextBlock();SetBoldLines(temporary,bold?1000:0);SetContent(temporary,value);
            while(temporary.Inlines.FirstInline is {} inline){temporary.Inlines.Remove(inline);block.Inlines.Add(inline);}
        }
        while(scan<text.Length && attempts++<256)
        {
            var at=text.IndexOfAny(['*','['],scan);if(at<0)break;
            if(text.AsSpan(at).StartsWith("**"))
            {
                var end=text.IndexOf("**",at+2,StringComparison.Ordinal);
                if(end>at+2){Plain(text[offset..at]);Plain(text[(at+2)..end],true);offset=end+2;scan=offset;continue;}
            }
            if(text[at]=='[')
            {
                var close=text.IndexOf(']',at+1);
                if(close>at && close-at<=256 && close+1<text.Length && text[close+1]=='(')
                {
                    var end=close+2;var depth=1;
                    while(end<text.Length && depth>0 && end-close<=4098){if(text[end]=='(')depth++;else if(text[end]==')')depth--;if(depth>0)end++;}
                    if(depth==0 && end<text.Length)
                    {
                        var address=text[(close+2)..end];
                        if(Overlay.Core.MessageCardParser.SafeUrl(address))
                        {Plain(text[offset..at]);var link=new Hyperlink(new Run(text[(at+1)..close])){Foreground=new SolidColorBrush(Color.FromRgb(0,95,184)),ToolTip=address};link.Click+=(_,e)=>{Open(address);e.Handled=true;};block.Inlines.Add(link);offset=end+1;scan=offset;continue;}
                    }
                }
            }
            scan=at+1;
        }
        Plain(text[offset..]);
    }
}
