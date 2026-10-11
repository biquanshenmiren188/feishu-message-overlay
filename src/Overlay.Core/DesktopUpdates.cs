using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Overlay.Core;

public sealed record DesktopRelease(string Tag, string AssetName, Uri Download, long Size, string Sha256);
public sealed record UpdateManifest(int Protocol, string Version, Dictionary<string,string> Files);

public static class DesktopUpdates
{
    public const string Repository="biquanshenmiren188/feishu-message-overlay";
    public const long MaximumDownload=256L*1024*1024;
    public static Version ParseVersion(string tag)
    {
        if(!Regex.IsMatch(tag,@"^v[0-9]{4}\.[0-9]{2}\.[0-9]{2}\.[0-9]{1,6}$"))throw new InvalidDataException("Invalid release version");
        var v=Version.Parse(tag[1..]);
        _=new DateTime(v.Major,v.Minor,v.Build);
        return v;
    }
    public static DesktopRelease? SelectRelease(string json,string current)
    {
        using var doc=JsonDocument.Parse(json);var r=doc.RootElement;
        if(r.GetProperty("draft").GetBoolean()||r.GetProperty("prerelease").GetBoolean())return null;
        var tag=r.GetProperty("tag_name").GetString()??"";
        if(ParseVersion(tag)<=ParseVersion(current))return null;
        var name=$"FeishuMessageOverlay-{tag}-win-x64.zip";
        var assets=r.GetProperty("assets").EnumerateArray().Where(a=>a.GetProperty("name").GetString()==name).ToArray();
        if(assets.Length!=1)throw new InvalidDataException("Release package missing or ambiguous");
        var a=assets[0];var size=a.GetProperty("size").GetInt64();
        var digest=a.GetProperty("digest").GetString()??"";
        var url=new Uri(a.GetProperty("browser_download_url").GetString()??"");
        if(a.GetProperty("state").GetString()!="uploaded"||size<=0||size>MaximumDownload||!Regex.IsMatch(digest,"^sha256:[a-fA-F0-9]{64}$")
          ||url.AbsoluteUri!=$"https://github.com/{Repository}/releases/download/{tag}/{name}")throw new InvalidDataException("Invalid release package");
        return new(tag,name,url,size,digest[7..].ToLowerInvariant());
    }
    public static string ChildPath(string root,string relative)
    {
        if(string.IsNullOrEmpty(relative)||relative.Contains('\\')||relative.Contains(':')||relative.StartsWith('/')||relative.EndsWith('/'))throw new InvalidDataException("Invalid package path");
        foreach(var segment in relative.Split('/'))
            if(segment is "" or "." or ".."||segment.EndsWith('.')||segment.EndsWith(' ')||segment.IndexOfAny(Path.GetInvalidFileNameChars())>=0
              ||Regex.IsMatch(segment,@"^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)",RegexOptions.IgnoreCase))throw new InvalidDataException("Unsafe package path");
        var fullRoot=Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
        var result=Path.GetFullPath(Path.Combine(fullRoot,relative.Replace('/',Path.DirectorySeparatorChar)));
        if(!result.StartsWith(fullRoot,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Package escaped staging directory");
        return result;
    }
    public static void VerifyHash(string file,string expected)
    {
        using var stream=File.OpenRead(file);
        if(!Convert.ToHexString(SHA256.HashData(stream)).Equals(expected,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Package checksum mismatch");
    }
    public static UpdateManifest ExtractVerified(string zip,string destination,string tag,string hash,long size)
    {
        if(new FileInfo(zip).Length!=size||size>MaximumDownload)throw new InvalidDataException("Package size mismatch");VerifyHash(zip,hash);
        if(Directory.Exists(destination))throw new IOException("Staging directory already exists");
        using var archive=ZipFile.OpenRead(zip);
        if(archive.Entries.Count>30000)throw new InvalidDataException("Too many package entries");
        var names=new HashSet<string>(StringComparer.OrdinalIgnoreCase);long total=0;
        foreach(var e in archive.Entries)
        {
            var name=e.FullName.TrimEnd('/');_ = ChildPath(destination,name);
            if(!names.Add(name)||((e.ExternalAttributes>>16)&0xF000)==0xA000||(e.ExternalAttributes&(int)FileAttributes.ReparsePoint)!=0)throw new InvalidDataException("Duplicate path or symlink");
            total=checked(total+e.Length);if(total>1024L*1024*1024)throw new InvalidDataException("Expanded package too large");
            CheckPackageName(name);
        }
        Directory.CreateDirectory(destination);
        foreach(var e in archive.Entries)
        {
            var path=ChildPath(destination,e.FullName.TrimEnd('/'));
            if(e.FullName.EndsWith('/'))Directory.CreateDirectory(path);
            else{Directory.CreateDirectory(Path.GetDirectoryName(path)!);e.ExtractToFile(path,false);}
        }
        return VerifyDirectory(destination,tag);
    }
    public static UpdateManifest VerifyDirectory(string directory,string tag)
    {
        RejectLinks(directory);
        var manifestPath=Path.Combine(directory,"update-manifest.json");
        if(new FileInfo(manifestPath).Length>8*1024*1024)throw new InvalidDataException("Manifest too large");
        var manifest=JsonSerializer.Deserialize<UpdateManifest>(File.ReadAllText(manifestPath))??throw new InvalidDataException("Missing manifest");
        if(manifest.Protocol!=1||manifest.Version!=tag||manifest.Files is null||manifest.Files.Count is 0 or >30000||!manifest.Files.ContainsKey("FeishuMessageOverlay.exe"))throw new InvalidDataException("Incompatible update manifest");
        var names=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach(var (name,hash) in manifest.Files)
        {
            CheckPackageName(name);
            if(!names.Add(name)||!Regex.IsMatch(hash,"^[a-fA-F0-9]{64}$"))throw new InvalidDataException("Invalid manifest hash");
            VerifyHash(ChildPath(directory,name),hash);
        }
        var actual=Directory.EnumerateFiles(directory,"*",SearchOption.AllDirectories).Select(p=>Path.GetRelativePath(directory,p).Replace('\\','/')).Where(n=>n!="update-manifest.json").ToHashSet(StringComparer.OrdinalIgnoreCase);
        if(!actual.SetEquals(names))throw new InvalidDataException("Unlisted package content");
        return manifest;
    }
    private static void CheckPackageName(string name)
    {
        if(name.Equals("storage-location.json",StringComparison.OrdinalIgnoreCase)||name.EndsWith(".dpapi",StringComparison.OrdinalIgnoreCase)||Path.GetFileName(name).Equals(".env",StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("User configuration in release");
    }
    private static void RejectLinks(string directory)
    {
        if((File.GetAttributes(directory)&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked directory is not supported");
        foreach(var entry in Directory.EnumerateFileSystemEntries(directory))
        {
            var attributes=File.GetAttributes(entry);
            if((attributes&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked content is not supported");
            if((attributes&FileAttributes.Directory)!=0)RejectLinks(entry);
        }
    }
    public static void CopyTree(string source,string target)
    {
        if((File.GetAttributes(source)&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked directory is not supported");
        Directory.CreateDirectory(target);
        foreach(var file in Directory.EnumerateFiles(source))
        {
            if((File.GetAttributes(file)&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked file is not supported");
            File.Copy(file,Path.Combine(target,Path.GetFileName(file)),true);
        }
        foreach(var child in Directory.EnumerateDirectories(source))CopyTree(child,Path.Combine(target,Path.GetFileName(child)));
    }
    // All transaction directories are exact siblings; unknown files/settings are retained.
    public static async Task<bool> InstallAsync(string install,string package,string tag,Func<string,Task<bool>> startAndVerify,Func<string,Task> restartOld)
    {
        install=Path.GetFullPath(install).TrimEnd(Path.DirectorySeparatorChar);
        if(!File.Exists(Path.Combine(install,"FeishuMessageOverlay.exe"))||Path.GetPathRoot(install)==install)throw new IOException("Not an application directory");
        VerifyDirectory(package,tag);
        var stage=install+".update-"+Guid.NewGuid().ToString("N");
        var backup=install+".backup-"+DateTime.UtcNow.ToString("yyyyMMddHHmmss")+"-"+Guid.NewGuid().ToString("N")[..8];
        var displaced=false;var installed=false;
        try
        {
            CopyTree(install,stage);CopyTree(package,stage);
            Directory.Move(install,backup);displaced=true;Directory.Move(stage,install);installed=true;
            if(!await startAndVerify(install))throw new IOException("Updated application did not become healthy");
            return true;
        }
        catch
        {
            if(displaced)
            {
                if(installed)await MoveAfterExitAsync(install,stage+".failed");
                await MoveAfterExitAsync(backup,install);
            }
            await restartOld(install);
            return false;
        }
    }
    private static async Task MoveAfterExitAsync(string source,string destination)
    {
        // Windows may release an exited process's image handles slightly later.
        for(var attempt=0;;attempt++)
        {
            try{Directory.Move(source,destination);return;}
            catch(IOException) when(attempt<20){await Task.Delay(250);}
            catch(UnauthorizedAccessException) when(attempt<20){await Task.Delay(250);}
        }
    }
}
