using System.IO;
using System.Text.Json;
namespace Overlay.App;
internal sealed record ConnectionSelection(string AppId,string[] ChatIds,string[] BotIds)
{
    private static string FileName=>Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"FeishuMessageOverlay","selection.json");
    internal static ConnectionSelection? Load()
    {
        try{var selected=JsonSerializer.Deserialize<ConnectionSelection>(File.ReadAllText(FileName));return selected is not null && ConnectionSettings.Validate(selected.AppId,"validation-only",selected.ChatIds,selected.BotIds) is null?selected:null;}catch{return null;}
    }
    internal static bool Save(ConnectionSettings settings)
    {
        if(App.SmokeMode)return true;
        if(ConnectionSettings.Validate(settings.AppId,settings.Secret,settings.ChatIds,settings.BotIds) is not null)return false;
        var existing=Load();if(existing is not null && existing.AppId==settings.AppId && existing.ChatIds.SequenceEqual(settings.ChatIds) && existing.BotIds.SequenceEqual(settings.BotIds))return true;
        try{Directory.CreateDirectory(Path.GetDirectoryName(FileName)!);File.WriteAllText(FileName+".tmp",JsonSerializer.Serialize(new ConnectionSelection(settings.AppId,settings.ChatIds,settings.BotIds)));File.Move(FileName+".tmp",FileName,true);return true;}catch{return false;}
    }
}
