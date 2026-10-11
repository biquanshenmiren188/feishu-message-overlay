using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using Overlay.Core;

internal static class DesktopUpdateTests
{
    internal static async Task RunAsync(Action<bool,string> check)
    {
        const string current="v2026.10.11.2",next="v2026.10.12.1";
        var root=Path.Combine(Path.GetTempPath(),"overlay-update-tests-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        string Hash(string path)=>Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
        void Reject(Action action,string name){var rejected=false;try{action();}catch(Exception e) when(e is IOException or InvalidDataException or ArgumentException or JsonException or FormatException){rejected=true;}check(rejected,"updater: "+name);}
        string Metadata(string tag=next,bool draft=false,bool prerelease=false,string? url=null,string? digest=null,long size=123)
        {
            var name=$"FeishuMessageOverlay-{tag}-win-x64.zip";
            return JsonSerializer.Serialize(new{tag_name=tag,draft,prerelease,assets=new[]{new{name,state="uploaded",size,digest=digest??"sha256:"+new string('a',64),browser_download_url=url??$"https://github.com/{DesktopUpdates.Repository}/releases/download/{tag}/{name}"}}});
        }
        void Manifest(string dir,string version=next)
        {
            var files=Directory.EnumerateFiles(dir,"*",SearchOption.AllDirectories).Where(p=>Path.GetFileName(p)!="update-manifest.json").ToDictionary(p=>Path.GetRelativePath(dir,p).Replace('\\','/'),Hash);
            File.WriteAllText(Path.Combine(dir,"update-manifest.json"),JsonSerializer.Serialize(new UpdateManifest(1,version,files)));
        }
        string Package(string name)
        {
            var dir=Path.Combine(root,name);Directory.CreateDirectory(Path.Combine(dir,"audio"));
            File.WriteAllText(Path.Combine(dir,"FeishuMessageOverlay.exe"),"new application");
            File.WriteAllText(Path.Combine(dir,"audio","notice.wav"),"sound");Manifest(dir);return dir;
        }
        string Install(string name)
        {
            var dir=Path.Combine(root,name);Directory.CreateDirectory(dir);
            File.WriteAllText(Path.Combine(dir,"FeishuMessageOverlay.exe"),"old application");
            File.WriteAllText(Path.Combine(dir,"storage-location.json"),"private local pointer");
            File.WriteAllText(Path.Combine(dir,"custom.wav"),"user sound");return dir;
        }
        try
        {
            check(DesktopUpdates.SelectRelease(Metadata(),current)?.Tag==next,"updater: select newer official version");
            check(DesktopUpdates.SelectRelease(Metadata(current),current) is null,"updater: same version does not download");
            check(DesktopUpdates.SelectRelease(Metadata("v2026.10.11.1"),current) is null,"updater: no downgrade");
            check(DesktopUpdates.SelectRelease(Metadata(draft:true),current) is null&&DesktopUpdates.SelectRelease(Metadata(prerelease:true),current) is null,"updater: ignore drafts and prereleases");
            Reject(()=>DesktopUpdates.SelectRelease(Metadata(url:"https://example.com/package.zip"),current),"reject unrelated package host");
            Reject(()=>DesktopUpdates.SelectRelease(Metadata(url:$"https://github.com/other/repo/releases/download/{next}/package.zip"),current),"reject unrelated repository");
            Reject(()=>DesktopUpdates.SelectRelease(Metadata(digest:"sha256:bad"),current),"require complete digest");
            Reject(()=>DesktopUpdates.SelectRelease(Metadata(size:DesktopUpdates.MaximumDownload+1),current),"reject oversized download");
            Reject(()=>DesktopUpdates.ParseVersion("v2026.02.30.1"),"reject invalid date");
            Reject(()=>DesktopUpdates.ParseVersion("v2026.10.12.1-beta"),"reject unsupported version format");
            foreach(var path in new[]{"../outside","/absolute","a/../../b","a\\..\\b","C:/Windows/file","a:stream","NUL.txt","a/COM1","a./b","a /b","a//b"})
                Reject(()=>DesktopUpdates.ChildPath(root,path),"reject unsafe path "+path);

            var package=Package("package");var zip=Path.Combine(root,"package.zip");ZipFile.CreateFromDirectory(package,zip);
            var digest=Hash(zip);var size=new FileInfo(zip).Length;
            check(DesktopUpdates.ExtractVerified(zip,Path.Combine(root,"extracted"),next,digest,size).Files.Count==2,"updater: extract and verify every file");
            Reject(()=>DesktopUpdates.ExtractVerified(zip,Path.Combine(root,"wrong-hash"),next,new string('0',64),size),"reject tampered download");
            Reject(()=>DesktopUpdates.ExtractVerified(zip,Path.Combine(root,"wrong-size"),next,digest,size+1),"reject partial download");
            Reject(()=>DesktopUpdates.VerifyDirectory(package,current),"reject manifest version mismatch");
            File.WriteAllText(Path.Combine(package,"audio","notice.wav"),"corrupted");
            Reject(()=>DesktopUpdates.VerifyDirectory(package,next),"reject changed payload hash");
            File.WriteAllText(Path.Combine(package,"audio","notice.wav"),"sound");
            File.WriteAllText(Path.Combine(package,"extra.txt"),"unlisted");
            Reject(()=>DesktopUpdates.VerifyDirectory(package,next),"reject unlisted payload");File.Delete(Path.Combine(package,"extra.txt"));
            File.WriteAllText(Path.Combine(package,"storage-location.json"),"injected");Manifest(package);
            Reject(()=>DesktopUpdates.VerifyDirectory(package,next),"reject bundled configuration override");File.Delete(Path.Combine(package,"storage-location.json"));Manifest(package);
            foreach(var attack in new[]{"traversal","duplicate","symlink"})
            {
                var badZip=Path.Combine(root,attack+".zip");
                using(var archive=ZipFile.Open(badZip,ZipArchiveMode.Create))
                {
                    var entry=archive.CreateEntry(attack=="traversal"?"../outside.txt":"payload.txt");
                    if(attack=="symlink")entry.ExternalAttributes=unchecked((int)0xA1FF0000);
                    if(attack=="duplicate")archive.CreateEntry("PAYLOAD.txt");
                }
                Reject(()=>DesktopUpdates.ExtractVerified(badZip,Path.Combine(root,attack),next,Hash(badZip),new FileInfo(badZip).Length),"reject ZIP "+attack);
            }
            var healthy=Install("healthy");var starts=0;var restores=0;
            check(await DesktopUpdates.InstallAsync(healthy,package,next,path=>{starts++;return Task.FromResult(File.ReadAllText(Path.Combine(path,"FeishuMessageOverlay.exe"))=="new application");},_=>{restores++;return Task.CompletedTask;}),"updater: successful transaction");
            check(starts==1&&restores==0&&File.ReadAllText(Path.Combine(healthy,"storage-location.json"))=="private local pointer"&&File.ReadAllText(Path.Combine(healthy,"custom.wav"))=="user sound","updater: preserve settings pointer and custom sound");
            check(Directory.GetDirectories(root,"healthy.backup-*").Length==1,"updater: retain previous program backup");
            foreach(var failure in new[]{"unhealthy","launch-exception"})
            {
                var old=Install(failure);restores=0;
                check(!await DesktopUpdates.InstallAsync(old,package,next,_=>failure=="unhealthy"?Task.FromResult(false):throw new IOException("synthetic launch failure"),path=>{restores++;check(File.ReadAllText(Path.Combine(path,"FeishuMessageOverlay.exe"))=="old application","updater: restore before restarting");return Task.CompletedTask;}),"updater: rolls back "+failure);
                check(restores==1&&File.ReadAllText(Path.Combine(old,"storage-location.json"))=="private local pointer","updater: restart previous version exactly once");
            }
            var locked=Install("locked");
            using(var held=new FileStream(Path.Combine(locked,"FeishuMessageOverlay.exe"),FileMode.Open,FileAccess.ReadWrite,FileShare.None))
            {
                starts=0;restores=0;
                check(!await DesktopUpdates.InstallAsync(locked,package,next,_=>{starts++;return Task.FromResult(true);},_=>{restores++;return Task.CompletedTask;}),"updater: locked source prevents replacement");
                check(starts==0&&restores==1,"updater: no new process on staging failure");
            }
            check(File.ReadAllText(Path.Combine(locked,"FeishuMessageOverlay.exe"))=="old application","updater: locked source remains intact");
        }
        finally{Directory.Delete(root,true);}
    }
}
