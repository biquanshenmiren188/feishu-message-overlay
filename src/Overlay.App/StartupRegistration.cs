using Microsoft.Win32;
namespace Overlay.App;
internal static class StartupRegistration
{
    private const string Key = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string Name = "FeishuMessageOverlay";
    internal static string CommandFor(string path) => "\"" + path + "\" --startup-visible";
    private static string Command => CommandFor(Environment.ProcessPath!);
    internal static bool IsOwned(object? value, string path) => Equals(value, CommandFor(path)) || Equals(value, "\"" + path + "\" --background");
    internal static bool MigrateEnabledLegacy()
    {
        if(App.SmokeMode) return false;
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(Key, true);
            if(key is null || !Equals(key.GetValue(Name), "\"" + Environment.ProcessPath + "\" --background")) return false;
            key.SetValue(Name, Command, RegistryValueKind.String); return true;
        }
        catch { return false; }
    }
    public static bool IsEnabled()
    {
        try { using var key=Registry.CurrentUser.OpenSubKey(Key); return IsOwned(key?.GetValue(Name),Environment.ProcessPath!); }
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
            if(existing is not null && !IsOwned(existing,Environment.ProcessPath!)) return false;
            if(enabled) key.SetValue(Name,Command,RegistryValueKind.String);
            else key.DeleteValue(Name,false);
            return true;
        }
        catch { return false; }
    }
}
