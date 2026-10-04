using System.Globalization;
using System.Windows.Data;
namespace Overlay.App;
public sealed class MessageLineConverter : IValueConverter
{
    public object Convert(object value,Type targetType,object parameter,CultureInfo culture)
    {
        var text=(value as string ?? "").TrimEnd('\r','\n');
        var index=text.IndexOfAny(['\r','\n']);
        if(parameter as string=="head")return index<0?text:text[..index];
        if(index<0)return parameter as string=="tailVisibility"?System.Windows.Visibility.Collapsed:"";
        var start=index+1;if(text[index]=='\r' && start<text.Length && text[start]=='\n')start++;
        var tail=text[start..];return parameter as string=="tailVisibility"?(tail.Length==0?System.Windows.Visibility.Collapsed:System.Windows.Visibility.Visible):tail;
    }
    public object ConvertBack(object value,Type targetType,object parameter,CultureInfo culture)=>throw new NotSupportedException();
}
