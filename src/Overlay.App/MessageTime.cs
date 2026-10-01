using System.Globalization;
using System.Windows.Data;
namespace Overlay.App;
// Display offset is explicit; OS timezone and message-body UTC text are untouched.
public sealed class MessageTime : IValueConverter
{
    public object Convert(object value,Type targetType,object parameter,CultureInfo culture)
    {
        if(value is not DateTimeOffset timestamp)return "";
        var local=timestamp.ToOffset(TimeSpan.FromHours(8));
        return parameter as string=="date"?local.ToString("yyyy-MM-dd HH:mm:ss",CultureInfo.InvariantCulture)+" UTC+8":local.ToString("HH:mm:ss",CultureInfo.InvariantCulture);
    }
    public object ConvertBack(object value,Type targetType,object parameter,CultureInfo culture)=>Binding.DoNothing;
}
