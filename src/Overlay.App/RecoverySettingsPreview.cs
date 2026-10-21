using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
namespace Overlay.App;
public partial class MainWindow
{
    internal void RenderRecoverySettings(string directory)
    {
        if(!App.SmokeMode)throw new InvalidOperationException("Preview requires isolated mode");
        Autostart.IsChecked=true;AutoRecovery.IsChecked=true;
        RecoveryStatus.Text="已开启；手动退出保持关闭，10 分钟内最多恢复 3 次。";
        SettingsPanel.Resources=Resources;Root.Children.Remove(SettingsPanel);SettingsPanel.Visibility=Visibility.Visible;
        var host=new Window{Title="Settings preview",Width=420,Height=950,Left=-12000,Top=-12000,ShowActivated=false,ShowInTaskbar=false,Background=Brushes.White,Content=SettingsPanel};
        host.Show();host.UpdateLayout();
        try
        {
            var image=new RenderTargetBitmap(630,1425,144,144,PixelFormats.Pbgra32);
            image.Render(host);var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(image));
            using var file=File.Create(Path.Combine(directory,"recovery-settings.png"));encoder.Save(file);
        }
        finally{host.Close();}
    }
}
