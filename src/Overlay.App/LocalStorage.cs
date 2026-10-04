using System.IO;
using System.Text.Json;
namespace Overlay.App;
internal static class LocalStorage
{
    private static string? directory;
    private static string ValidateLocation(string configured)
    {
        if(!Path.IsPathFullyQualified(configured))throw new IOException("Invalid application storage location");
        var full=Path.GetFullPath(configured);
        var userLocal=Path.GetFullPath(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"AppData","Local"))+Path.DirectorySeparatorChar;
        if(!full.StartsWith(userLocal,StringComparison.OrdinalIgnoreCase)
            ||!string.Equals(Path.GetFileName(full.TrimEnd(Path.DirectorySeparatorChar)),"FeishuMessageOverlay",StringComparison.OrdinalIgnoreCase))
            throw new IOException("Invalid application storage location");
        return full;
    }
    internal static void LocationContract()
    {
        var local=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"AppData","Local");
        if(ValidateLocation(Path.Combine(local,"FeishuMessageOverlay"))!=Path.Combine(local,"FeishuMessageOverlay"))
            throw new InvalidOperationException("Storage location contract");
        foreach(var invalid in new[]{"relative/FeishuMessageOverlay",Path.Combine(local,"other"),Path.Combine(local,"..","Roaming","FeishuMessageOverlay")})
        {try{ValidateLocation(invalid);throw new InvalidOperationException("Invalid location accepted");}catch(IOException){}}
    }
    internal static string ResolveExistingFile(string path)
    {
        if(string.IsNullOrEmpty(path)||!Path.IsPathFullyQualified(path)||File.Exists(path))return path;
        var logical=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"FeishuMessageOverlay")+Path.DirectorySeparatorChar;
        var full=Path.GetFullPath(path);
        if(!full.StartsWith(logical,StringComparison.OrdinalIgnoreCase))return path;
        var root=DirectoryPath.TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
        var candidate=Path.GetFullPath(Path.Combine(root,full[logical.Length..]));
        return candidate.StartsWith(root,StringComparison.OrdinalIgnoreCase)&&File.Exists(candidate)?candidate:path;
    }
    internal static string DirectoryPath
    {
        get
        {
            if(directory is not null)return directory;
            var marker=Path.Combine(AppContext.BaseDirectory,"storage-location.json");
            if(!App.SmokeMode&&File.Exists(marker))
            {
                using var document=JsonDocument.Parse(File.ReadAllText(marker));
                var configured=document.RootElement.GetProperty("directory").GetString()??"";
                return directory=ValidateLocation(configured);
            }
            var root=Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData,Environment.SpecialFolderOption.DoNotVerify);
            if(!Path.IsPathFullyQualified(root))root=Environment.GetEnvironmentVariable("LOCALAPPDATA")??"";
            if(!Path.IsPathFullyQualified(root))throw new IOException("Local application data is unavailable");
            return directory=Path.Combine(root,"FeishuMessageOverlay");
        }
    }
    internal static void AtomicWrite(string path,byte[] bytes)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temp=path+"."+Guid.NewGuid().ToString("N")+".tmp";
        try
        {
            using(var file=new FileStream(temp,FileMode.CreateNew,FileAccess.Write,FileShare.None)){file.Write(bytes);file.Flush(true);}
            File.Move(temp,path,true);
        }
        finally{try{File.Delete(temp);}catch(IOException){}catch(UnauthorizedAccessException){}}
    }
}
