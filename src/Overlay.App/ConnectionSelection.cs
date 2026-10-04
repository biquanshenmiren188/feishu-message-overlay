using System.IO;
using System.Text.Json;
namespace Overlay.App;
internal sealed record ConnectionSelection(string AppId,string[] ChatIds,string[] BotIds)
{
    private static string FileName=>Path.Combine(LocalStorage.DirectoryPath,"selection.json");
    internal static string LoadState {get;private set;}="not_loaded";
    internal static ConnectionSelection? Load()
    {
        try{var selected=JsonSerializer.Deserialize<ConnectionSelection>(File.ReadAllText(FileName));var valid=selected is not null && ConnectionSettings.Validate(selected.AppId,"validation-only",selected.ChatIds,selected.BotIds) is null;LoadState=valid?"loaded":"invalid_configuration";return valid?selected:null;}
        catch(FileNotFoundException){LoadState="missing";return null;}catch(DirectoryNotFoundException){LoadState="missing";return null;}
        catch(UnauthorizedAccessException){LoadState="access_denied";return null;}catch(IOException){LoadState="io_error";return null;}catch(JsonException){LoadState="invalid_json";return null;}
    }
    internal static bool Save(ConnectionSettings settings)
    {
        if(App.SmokeMode)return true;
        if(ConnectionSettings.Validate(settings.AppId,settings.Secret,settings.ChatIds,settings.BotIds) is not null)return false;
        var existing=Load();if(LoadState is not ("loaded" or "missing"))return false;
        if(existing is not null && existing.AppId==settings.AppId && existing.ChatIds.SequenceEqual(settings.ChatIds) && existing.BotIds.SequenceEqual(settings.BotIds))return true;
        try{LocalStorage.AtomicWrite(FileName,JsonSerializer.SerializeToUtf8Bytes(new ConnectionSelection(settings.AppId,settings.ChatIds,settings.BotIds)));return true;}catch(IOException){return false;}catch(UnauthorizedAccessException){return false;}
    }
}
