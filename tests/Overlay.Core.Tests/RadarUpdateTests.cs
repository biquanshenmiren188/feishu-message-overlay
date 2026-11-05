using System.Security.Cryptography;
using System.Text.Json;
using Overlay.Core;

internal static class RadarUpdateTests
{
    internal static void Run(Action<bool,string> check)
    {
        using var key=RSA.Create(2048);using var other=RSA.Create(2048);
        const string current="v2026.11.01.1",next="v2026.11.05.1";
        string Envelope(string tag=next,int protocol=1,long size=123,string? hash=null,string? commit=null,bool tamper=false)
        {
            var bytes=JsonSerializer.SerializeToUtf8Bytes(new{Version=tag,Protocol=protocol,Size=size,Sha256=hash??new string('a',64),SourceCommit=commit??new string('b',40)});
            var signature=key.SignData(bytes,HashAlgorithmName.SHA256,RSASignaturePadding.Pss);
            if(tamper)bytes[0]^=1;
            return JsonSerializer.Serialize(new{payload=Convert.ToBase64String(bytes),signature=Convert.ToBase64String(signature)});
        }
        void Reject(string json,string name,string? publicKey=null)
        {
            var rejected=false;try{RadarDesktopUpdates.SelectRelease(json,current,publicKey??key.ExportSubjectPublicKeyInfoPem());}catch(InvalidDataException){rejected=true;}
            check(rejected,"radar updater: "+name);
        }
        var release=RadarDesktopUpdates.SelectRelease(Envelope(),current,key.ExportSubjectPublicKeyInfoPem());
        check(release?.Tag==next&&release.Download.AbsoluteUri==RadarDesktopUpdates.BaseUrl+next+"/FeishuMessageOverlay-"+next+"-win-x64.zip","radar updater: signed version and fixed download host");
        check(RadarDesktopUpdates.SelectRelease(Envelope(current),current,key.ExportSubjectPublicKeyInfoPem()) is null,"radar updater: same version ignored");
        check(RadarDesktopUpdates.SelectRelease(Envelope("v2026.10.26.1"),current,key.ExportSubjectPublicKeyInfoPem()) is null,"radar updater: downgrade ignored");
        Reject(Envelope(tamper:true),"tampered payload rejected");
        Reject(Envelope(),"wrong signing key rejected",other.ExportSubjectPublicKeyInfoPem());
        Reject(Envelope(protocol:2),"unsupported protocol");
        Reject(Envelope(size:0),"zero size");
        Reject(Envelope(size:DesktopUpdates.MaximumDownload+1),"oversize");
        Reject(Envelope(hash:"bad"),"bad hash");
        Reject(Envelope(commit:"main"),"immutable source required");
        Reject(Envelope(tag:"v2026.02.30.1"),"invalid date");
        Reject("{}","unsigned manifest");
        Reject("<html>login</html>","login page is not a release");
        Reject(new string('x',65537),"bounded metadata");
    }
}
