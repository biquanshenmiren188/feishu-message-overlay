using System.IO;
namespace Overlay.App;
internal static class LocalStorage
{
    private static string? directory;
    internal static string DirectoryPath
    {
        get
        {
            if(directory is not null)return directory;
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
