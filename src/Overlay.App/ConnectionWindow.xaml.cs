using System.Windows;
namespace Overlay.App;
public partial class ConnectionWindow : Window
{
    public ConnectionSettings? Settings { get; private set; }
    private ConnectionSettings? existing;
    public ConnectionWindow(ConnectionSettings? credentials = null)
    {
        InitializeComponent(); if (credentials is not null) UseCredentials(credentials);
        Closed += (_, _) => { SecretInput.Clear(); if (existing is not null) existing.Secret = ""; };
    }
    private void UseCredentials(ConnectionSettings credentials)
    {
        existing = credentials; AppIdInput.Text = credentials.AppId; AppIdInput.IsReadOnly = true;
        SecretInput.IsEnabled = false; SecretHint.Text = "使用本机程序持有的应用凭证 · 密钥不会显示";
    }
    private void LoadSavedClick(object sender, RoutedEventArgs e)
    {
        var credentials = CredentialVault.LoadOnUserRequest();
        if (credentials is null) { Validation.Text = "未找到可用的本机加密配置；没有读取浏览器或客户端凭证"; return; }
        UseCredentials(credentials);
    }
    private void SubmitClick(object sender, RoutedEventArgs e)
    {
        var chats = ConnectionSettings.Split(ChatInput.Text); var bots = ConnectionSettings.Split(BotInput.Text);
        var appId = AppIdInput.Text.Trim(); var secret = existing?.Secret ?? SecretInput.Password;
        var error = ConnectionSettings.Validate(appId, secret, chats, bots);
        if (error is not null) { Validation.Text = error; return; }
        if (Consent.IsChecked != true) { Validation.Text = "请先确认应用权限和本次连接用途"; return; }
        Settings = new() { AppId = appId, Secret = secret, ChatIds = chats, BotIds = bots }; SecretInput.Clear(); DialogResult = true;
    }
    private void CloseClick(object sender, RoutedEventArgs e) => Close();
}
