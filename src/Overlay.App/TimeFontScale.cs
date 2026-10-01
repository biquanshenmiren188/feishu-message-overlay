using System.Globalization;
using System.Windows.Data;
namespace Overlay.App;
public sealed class TimeFontScale : IValueConverter
{
    public object Convert(object value,Type targetType,object parameter,CultureInfo culture)=>value is double size?Math.Clamp(size*.9,11,29):12.6;
    public object ConvertBack(object value,Type targetType,object parameter,CultureInfo culture)=>Binding.DoNothing;
}
public sealed class BodyLineHeight : IValueConverter
{
    public object Convert(object value,Type targetType,object parameter,CultureInfo culture)=>value is double size?Math.Max(size*1.3,size+3):16.9;
    public object ConvertBack(object value,Type targetType,object parameter,CultureInfo culture)=>Binding.DoNothing;
}
