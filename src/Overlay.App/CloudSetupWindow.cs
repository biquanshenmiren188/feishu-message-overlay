using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace Overlay.App;

internal sealed class CloudSetupWindow : Window
{
    private readonly PasswordBox secret=new(){Height=32,MaxLength=256,Margin=new Thickness(0,6,0,14)};
    private readonly TextBlock status=new(){TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,10,0,0)};
    private readonly Button submit=new(){Content="验证并安全保存",Height=34};
    private readonly string appId;
    private readonly string? receipt;
    private bool busy;

    internal CloudSetupWindow(string? receiptPath)
    {
        receipt=receiptPath;
        appId=ConnectionSelection.Load()?.AppId??"";
        Title="飞书云接收 · 安全配置";Width=470;Height=390;
        WindowStartupLocation=WindowStartupLocation.CenterScreen;ResizeMode=ResizeMode.NoResize;
        Background=Brushes.White;Foreground=Brushes.Black;FontFamily=new FontFamily("Microsoft YaHei");FontSize=13;
        var panel=new StackPanel{Margin=new Thickness(22)};Content=panel;
        panel.Children.Add(new TextBlock{Text="只需您本人输入一次 App Secret",FontSize=17,FontWeight=FontWeights.SemiBold,Margin=new Thickness(0,0,0,12)});
        panel.Children.Add(new TextBlock{Text="应用："+appId,TextWrapping=TextWrapping.Wrap});
        panel.Children.Add(new TextBlock{Text="凭证经签名认证的 HTTPS 直接发送至您已批准的服务器，保存在服务专用受限目录；不会写入聊天或日志。此步只验证并保存，不会启动第二条飞书连接。",TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,12,0,12)});
        panel.Children.Add(new TextBlock{Text="App Secret（不显示明文）"});panel.Children.Add(secret);
        panel.Children.Add(submit);panel.Children.Add(status);
        submit.IsEnabled=!string.IsNullOrEmpty(appId);
        if(!submit.IsEnabled)status.Text="未找到现有应用身份，请保留当前配置并检查启动目录。";
        submit.Click+=async (_,_)=>await SaveAsync();
        Closing+=(_,e)=>{if(busy){e.Cancel=true;status.Text="正在安全验证，请等待结果后再关闭。";}else secret.Clear();};
    }

    private async Task SaveAsync()
    {
        if(busy)return;
        if(secret.Password.Length<8){status.Text="请输入该应用的 App Secret。";return;}
        busy=true;submit.IsEnabled=false;status.Text="正在验证并安全保存，请勿把密钥发送到聊天……";
        try
        {
            var pin=Preferences.Load().PinnedChatId;
            var data=new{appId,appSecret=secret.Password,pinnedGroupId=pin.Length>0?PublicWebPublisher.Digest(pin):""};
            secret.Clear();
            using var result=await PublicWebPublisher.SendControlAsync("/radar/api/robot-push/configure",data);
            var saved=result.RootElement.GetProperty("configured").GetBoolean();
            if(!saved)throw new InvalidOperationException();
            status.Text="已验证并保存。当前仍由电脑接收；后续将受控切换为唯一云接收，不会同时开启两条连接。";
            if(receipt is not null)await File.WriteAllTextAsync(receipt,JsonSerializer.Serialize(new{configured=true,appId,phase="prepared",receiverStarted=false,secretExportedToTools=false}));
        }
        catch {status.Text="未能确认保存成功。请检查应用密钥或网络后重试；不会显示原始错误或密钥。";}
        finally {busy=false;submit.IsEnabled=true;}
    }
}
