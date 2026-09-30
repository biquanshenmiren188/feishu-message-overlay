using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
namespace Overlay.App;
public partial class RegistrationWindow : Window
{
    private Process? child;
    private readonly CancellationTokenSource stop = new();
    private ConnectionSettings? result;
    private bool keepResult;
    private static void Receipt(string state, string? appId = null)
    {
        if (App.SetupReceipt is not { } path) return;
        try { Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!); File.WriteAllText(path, JsonSerializer.Serialize(new { state, appId })); } catch (IOException) { }
    }
    public ConnectionSettings? Result => keepResult ? result : null;
    public RegistrationWindow() => InitializeComponent();
    internal Task BeginAsync() => RegisterAsync();
    private async void BeginClick(object sender, RoutedEventArgs e) => await RegisterAsync();
    private async Task RegisterAsync()
    {
        if (child is not null || App.SmokeMode) return;
        BeginButton.IsEnabled = false; Progress.Text = "正在获取飞书官方确认页 · 请自行扫码核对权限"; Receipt("starting");
        try
        {
            var script = Path.Combine(AppContext.BaseDirectory, "bridge", "register.mjs");
            var info = new ProcessStartInfo(ConnectionSettings.FindNode()) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true, WorkingDirectory = Path.GetDirectoryName(script)! };
            info.ArgumentList.Add(script); child = Process.Start(info) ?? throw new InvalidOperationException();
            _ = DiscardErrorsAsync(child);
            while (!stop.IsCancellationRequested)
            {
                var line = await child.StandardOutput.ReadLineAsync(stop.Token); if (line is null) break;
                if (line.Length > 32768) throw new InvalidOperationException();
                using var document = JsonDocument.Parse(line); var record = document.RootElement;
                var kind = record.GetProperty("kind").GetString();
                if (kind == "authorize")
                {
                    var url = new Uri(record.GetProperty("url").GetString()!);
                    if (url.Scheme != "https" || url.Host is not ("accounts.feishu.cn" or "open.feishu.cn")) throw new InvalidOperationException();
                    Process.Start(new ProcessStartInfo(url.AbsoluteUri) { UseShellExecute = true });
                    Progress.Text = "官方确认页已打开 · 请扫码并核对权限；本软件等待结果，密钥不会显示";
                    Receipt("awaiting_user_scan_and_permission_review");
                }
                else if (kind == "registered")
                {
                    result = new() { AppId = record.GetProperty("appId").GetString()!, Secret = record.GetProperty("secret").GetString()! };
                    if (!result.AppId.StartsWith("cli_", StringComparison.Ordinal) || string.IsNullOrEmpty(result.Secret)) throw new InvalidOperationException();
                    Progress.Text = "官方返回应用创建成功 · 尚未验证群权限。应用ID：" + result.AppId;
                    Receipt("registered_not_connected", result.AppId);
                    ContinueButton.IsEnabled = true; return;
                }
                else throw new InvalidOperationException();
            }
            Progress.Text = "扫码未完成、已取消或创建失败 · 未获取应用凭证";
            Receipt("not_completed");
        }
        catch (OperationCanceledException) { }
        catch (Exception) { if (!stop.IsCancellationRequested) { Progress.Text = "官方扫码失败 · 可能未开放此租户流程或网络不可用；没有输出密钥。可使用已有应用的本机输入方式。"; Receipt("registration_failed"); } }
    }
    private async Task DiscardErrorsAsync(Process process)
    {
        var buffer = new char[4096];
        try { while (await process.StandardError.ReadAsync(buffer, stop.Token) > 0) Array.Clear(buffer); }
        catch (OperationCanceledException) { } catch (IOException) { }
        finally { Array.Clear(buffer); }
    }
    private void ContinueClick(object sender, RoutedEventArgs e)
    {
        if (result is null) return;
        if (SaveConsent.IsChecked == true && !CredentialVault.Save(result)) { Progress.Text = "本机加密保存失败 · 未保存；取消保存勾选可仅用本次会话"; return; }
        keepResult = true; DialogResult = true;
    }
    private void CancelClick(object sender, RoutedEventArgs e) => Close();
    private void ClosingHandler(object? sender, CancelEventArgs e)
    {
        stop.Cancel();
        if (child is not null) { try { child.StandardInput.Close(); if (!child.HasExited) child.Kill(entireProcessTree: true); } catch (InvalidOperationException) { } }
        if (!keepResult && result is not null) result.Secret = "";
    }
}
