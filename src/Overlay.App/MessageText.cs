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
        block.Inlines.Clear(); var offset = 0;
        foreach (Match match in Links().Matches(text))
        {
            if (match.Index > offset) block.Inlines.Add(new Run(text[offset..match.Index]));
            var address=match.Value;
            if(!address.Contains('?'))address=address.TrimEnd('.',',','!');
            while(address.EndsWith(')') && address.Count(c=>c==')')>address.Count(c=>c=='('))address=address[..^1];
            var link = new Hyperlink(new Run(address)) { Foreground = new SolidColorBrush(Color.FromRgb(96,205,255)), ToolTip = address };
            // Never launch during parsing/binding. Only an explicit click opens HTTP(S).
            link.Click += (_, e) => { Open(address); e.Handled = true; };
            block.Inlines.Add(link); offset = match.Index + address.Length;
        }
        if (offset < text.Length) block.Inlines.Add(new Run(text[offset..]));
    }
}
