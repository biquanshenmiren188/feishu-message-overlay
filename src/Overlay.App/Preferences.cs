using System.IO;
using System.Text.Json;
namespace Overlay.App;
// Only appearance is persisted. No messages, account IDs, group IDs, or secrets.
public sealed record Preferences
{
    public double Width { get; init; } = 360;
    public double Height { get; init; } = 460;
    public double Opacity { get; init; } = .96;
    public string AudioPath { get; init; } = "";
    public bool Topmost { get; init; } = true;
    public bool Sound { get; init; } = false;
    public string Font { get; init; } = "Microsoft YaHei UI";
    public double FontSize { get; init; } = 14;
    private static string PathName => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "FeishuMessageOverlay", "appearance.json");
    public static Preferences Load()
    {
        try { return JsonSerializer.Deserialize<Preferences>(File.ReadAllText(PathName)) ?? new(); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException) { return new(); }
    }
    public bool Save()
    {
        try { Directory.CreateDirectory(Path.GetDirectoryName(PathName)!); File.WriteAllText(PathName + ".tmp", JsonSerializer.Serialize(this)); File.Move(PathName + ".tmp", PathName, true); return true; }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return false; }
    }
}
