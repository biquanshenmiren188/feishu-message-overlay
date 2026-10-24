using System.IO;
using System.Text.Json;
using System.Windows;

namespace Overlay.App;
public partial class MainWindow
{
    private DesktopPushBinding? pushBinding;
    private bool changingPushBinding;
    private Func<string,Task> verifyPushBinding=DesktopPushBinding.VerifyAsync;
    private Func<string,CloudMessageSource>? bindingSourceFactory;
    private void InitializePushBinding()
    {
        // UI contracts must never read this user's real binding.
        if(!App.SmokeMode)pushBinding=new(Path.Combine(LocalStorage.DirectoryPath,"desktop-push-code.dpapi"));
        UpdatePushBindingLabel();
    }
    private void UpdatePushBindingLabel()
    {
        PushBindingStatus.Text=pushBinding is {Readable:false}?"本机绑定无法读取，已暂停接收。请重新绑定，或明确解绑以恢复全部接收。"
            :pushBinding is {Bound:true}?"已绑定 · 尾号 "+pushBinding.Code![^4..]+"，按此码的电脑和卡片设置接收。"
            :"未绑定 · 接收全部消息与行情卡片。";
        BindPushCode.IsEnabled=!changingPushBinding;
        UnbindPushCode.IsEnabled=!changingPushBinding&&pushBinding is {Code:not ""};
        UnbindPushCode.Opacity=UnbindPushCode.IsEnabled?1:.45;
        PushCodeInput.IsEnabled=!changingPushBinding;
    }
    private async void BindPushCodeClick(object sender,RoutedEventArgs e)
    {var code=PushCodeInput.Password.Trim();if(code.Length==0){PushBindingStatus.Text="请输入自己的 8 位数字推送码。";return;}await ChangePushBindingAsync(code);}
    private async void UnbindPushCodeClick(object sender,RoutedEventArgs e)=>await ChangePushBindingAsync("");
    private async Task ChangePushBindingAsync(string code)
    {
        if(changingPushBinding||pushBinding is null)return;
        if(code.Length>0&&!DesktopPushBinding.Valid(code)){PushBindingStatus.Text="请输入 8 位数字推送码。";return;}
        changingPushBinding=true;UpdatePushBindingLabel();PushBindingStatus.Text=code.Length>0?"正在验证推送码……":"正在解除本机绑定……";
        var committed=false;
        try
        {
            if(!await pushBinding.ChangeAsync(code,verifyPushBinding))
            {PushBindingStatus.Text="本机安全保存失败，原绑定保持不变。请检查配置目录权限后重试。";return;}
            committed=true;
            PushCodeInput.Clear();
            // Recreate the immutable source; old in-flight responses cannot join the new identity.
            await StartCloudAsync();UpdatePushBindingLabel();
        }
        catch(ArgumentException){PushBindingStatus.Text="请输入 8 位数字推送码，原绑定保持不变。";}
        catch{PushBindingStatus.Text=committed?"本机绑定已保存，重新连接暂未完成。请重新点击连接或重启软件；不会退回其他人的规则。":"推送码验证失败或服务暂不可用，原绑定保持不变。请核对推送码后重试。";}
        finally{changingPushBinding=false;BindPushCode.IsEnabled=true;UnbindPushCode.IsEnabled=pushBinding.Code!="";UnbindPushCode.Opacity=UnbindPushCode.IsEnabled?1:.45;PushCodeInput.IsEnabled=true;}
    }
    private async Task<JsonElement> SendScopedCoinRulesAsync(string code,object request)
    {
        if(pushBinding?.Code!=code||source is not CloudMessageSource {CanManage:true})throw new InvalidOperationException("推送码已切换或规则连接中断，请重新打开管理窗口。");
        using var response=await PublicWebPublisher.SendControlAsync("/radar/api/robot-push/control",new{action="coin-rules",pushCode=code,request});
        if(pushBinding.Code!=code)throw new InvalidOperationException("推送码已切换，请重新打开管理窗口。");
        var root=response.RootElement;
        if(!root.TryGetProperty("ok",out var ok)||!ok.GetBoolean())throw new InvalidOperationException(root.TryGetProperty("error",out var error)?error.GetString():"规则服务暂不可用");
        return root.GetProperty("data").Clone();
    }
}
