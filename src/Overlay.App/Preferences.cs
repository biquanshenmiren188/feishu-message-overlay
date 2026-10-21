using System.IO;
using System.Text.Json;
namespace Overlay.App;
// UI preferences and the selected pinned group ID only. No messages or secrets.
public sealed record Preferences
{
    internal static long WriteCount {get;private set;}
    internal static string LoadState {get;private set;}="not_loaded";
    internal static string StoragePath=>PathName;
    public double Width { get; init; } = 360;
    public double? MessagePaneWidth { get; init; }
    public double Height { get; init; } = 460;
    public double Opacity { get; init; } = .95;
    public string AudioPath { get; init; } = "";
    public bool Topmost { get; init; } = true;
    public bool Sound { get; init; } = true;
    public bool AutoRecovery { get; init; } = true;
    public string PinnedChatId {get;init;}="";
    public bool AutoListenJoined {get;init;} = false;
    public bool AutoScroll { get; init; } = true;
    public int DwellSeconds { get; init; } = 15;
    public string Font { get; init; } = "Microsoft YaHei";
    public double FontSize { get; init; } = 13;
    internal static string? ContractPath {get;set;}
    private static string PathName => App.SmokeMode && ContractPath is not null?ContractPath:Path.Combine(LocalStorage.DirectoryPath,"appearance.json");
    internal double CloudTextWidth(double currentWidth,double cardsWidth)
    {
        if(MessagePaneWidth is {} text && double.IsFinite(text) && text>=300)return Math.Clamp(text,300,1200);
        // Legacy cloud preferences stored the total window width, including the card pane.
        return Math.Clamp(currentWidth>=cardsWidth+300?currentWidth-cardsWidth:currentWidth,300,1200);
    }
    public static Preferences Load()
    {
        try { var prefs=JsonSerializer.Deserialize<Preferences>(File.ReadAllText(PathName),new JsonSerializerOptions{PropertyNameCaseInsensitive=true});LoadState=prefs is null?"invalid_json":"loaded";return prefs??new(); }
        catch(FileNotFoundException){LoadState="missing";return new();}
        catch(DirectoryNotFoundException){LoadState="missing";return new();}
        catch(UnauthorizedAccessException){LoadState="access_denied";return new();}
        catch(IOException){LoadState="io_error";return new();}
        catch(JsonException){LoadState="invalid_json";return new();}
    }
    public bool Save()
    {
        try {
            if(LoadState is not ("loaded" or "missing" or "not_loaded"))return false;
            if(LoadState=="missing" && File.Exists(PathName))return false;
            LocalStorage.AtomicWrite(PathName,JsonSerializer.SerializeToUtf8Bytes(this));LoadState="loaded";WriteCount++;return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return false; }
    }
}
