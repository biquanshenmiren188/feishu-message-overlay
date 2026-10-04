using System.IO;
using System.Text.Json;
namespace Overlay.App;
internal static class CloudMode
{
    private static string PathName=>Path.Combine(LocalStorage.DirectoryPath,"cloud-source.json");
    // Presence with corrupt data fails closed: never silently reconnect a local SDK.
    internal static bool Enabled=>!App.SmokeMode && File.Exists(PathName);
    internal static void Set(bool enabled)
    {
        if(enabled)LocalStorage.AtomicWrite(PathName,JsonSerializer.SerializeToUtf8Bytes(new{enabled=true}));
        else if(File.Exists(PathName))File.Delete(PathName);
    }
}
