using Microsoft.Win32;
namespace Overlay.App;
internal static class StartupRegistration
{
    private const string Key = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string Name = "FeishuMessageOverlay";
    private static string Command => "\"" + Environment.ProcessPath + "\" --background";
    public static bool IsEnabled()
    {
        try { using var key=Registry.CurrentUser.OpenSubKey(Key); return Equals(key?.GetValue(Name),Command); }
        catch { return false; }
    }
    // Only called by the user's switch. Never runs during startup or smoke checks.
    public static bool TrySet(bool enabled)
    {
        if(App.SmokeMode) return false;
        try
        {
            using var key=Registry.CurrentUser.CreateSubKey(Key);
            var existing=key.GetValue(Name);
            if(existing is not null && !Equals(existing,Command)) return false;
            if(enabled) key.SetValue(Name,Command,RegistryValueKind.String);
            else key.DeleteValue(Name,false);
            return true;
        }
        catch { return false; }
    }
}
