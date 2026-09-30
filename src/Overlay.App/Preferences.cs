using System.IO;
using System.Text.Json;
namespace Overlay.App;
// Only appearance is persisted. No messages, account IDs, group IDs, or secrets.
public sealed record Preferences
{
    internal static long WriteCount {get;private set;}
    public double Width { get; init; } = 360;
    public double Height { get; init; } = 460;
    public double Opacity { get; init; } = .95;
    public string AudioPath { get; init; } = "";
    public bool Topmost { get; init; } = true;
    public bool Sound { get; init; } = false;
    public bool AutoScroll { get; init; } = true;
    public int DwellSeconds { get; init; } = 15;
    public string Font { get; init; } = "Microsoft YaHei";
    public double FontSize { get; init; } = 14;
    internal static string? ContractPath {get;set;}
    private static string PathName => App.SmokeMode && ContractPath is not null?ContractPath:Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "FeishuMessageOverlay", "appearance.json");
    public static Preferences Load()
    {
        try { return JsonSerializer.Deserialize<Preferences>(File.ReadAllText(PathName)) ?? new(); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException) { return new(); }
    }
    public bool Save()
    {
        try { Directory.CreateDirectory(Path.GetDirectoryName(PathName)!); File.WriteAllText(PathName + ".tmp", JsonSerializer.Serialize(this)); File.Move(PathName + ".tmp", PathName, true); WriteCount++;return true; }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return false; }
    }
}
