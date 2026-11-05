using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Overlay.Core;

public static class RadarDesktopUpdates
{
    public const string BaseUrl="https://leida.shenmiren.work/desktop-updates/";
    public const string PublicKey="""
-----BEGIN PUBLIC KEY-----
MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAndoP4Pf6MkS8sMpzJY8A
NmyLKmS5vYMXsRZ0lbuAuFzjYKKzNv4vIZjtJ+4koDjg4QHyt79NIoridf7D20Yz
qC3cXb2vY7mBKEwGRh5+zhX7Wc6ZYqA7OIFaOhnX9Z94eHfPD7Rhtb8bnA4BcRoz
ClEIo/AsaPZSu81w9CnL73iVxrM4Y1k/oFsz3Uenox82vLxpT/+TjmjYUmd7XjAW
Q2VQTJpQmzfw4chQVUl6uIpnmU61VhVffm79xb/g//CYUaVoF98qMhFRPwcKrp/Z
5Po6WfAmQkf1h8eOoKrBTRO/gaU5CdNfaZkGSI/5ar9DL4X/Gng99Lgvxff9CUtS
U7rXYKXucMghjiTrZEcT7nSRiX1NjnLLBxZdWw5Iopum0A6YviORpfdSFovnCJz2
ImpR2VjNHV00tndB2sTrw2RW+azDDbbPkHnah8GcnA22rzzIfi9QGjgSKfs3SL2p
AfET8jCYjAQ4PiaovH3hlMovbYyeUvBwJwlATJhh9JqBAgMBAAE=
-----END PUBLIC KEY-----
""";
    public static DesktopRelease? SelectRelease(string json,string current,string publicKey=PublicKey)
    {
        if(json.Length>65536)throw new InvalidDataException("Release metadata too large");
        try
        {
            using var envelope=JsonDocument.Parse(json);
            var bytes=Convert.FromBase64String(envelope.RootElement.GetProperty("payload").GetString()!);
            var signature=Convert.FromBase64String(envelope.RootElement.GetProperty("signature").GetString()!);
            using var rsa=RSA.Create();rsa.ImportFromPem(publicKey);
            if(!rsa.VerifyData(bytes,signature,HashAlgorithmName.SHA256,RSASignaturePadding.Pss))throw new InvalidDataException("Release signature mismatch");
            using var payload=JsonDocument.Parse(bytes);var p=payload.RootElement;
            var tag=p.GetProperty("Version").GetString()!;
            var version=DesktopUpdates.ParseVersion(tag);
            var size=p.GetProperty("Size").GetInt64();var hash=p.GetProperty("Sha256").GetString()!;
            if(p.GetProperty("Protocol").GetInt32()!=1||size<=0||size>DesktopUpdates.MaximumDownload
                ||!Regex.IsMatch(hash,"^[a-f0-9]{64}$")||!Regex.IsMatch(p.GetProperty("SourceCommit").GetString()!,"^[a-f0-9]{40}$"))
                throw new InvalidDataException("Invalid signed release");
            if(version<=DesktopUpdates.ParseVersion(current))return null;
            var name=$"FeishuMessageOverlay-{tag}-win-x64.zip";
            return new(tag,name,new Uri(BaseUrl+tag+"/"+name),size,hash);
        }
        catch(Exception e) when(e is JsonException or FormatException or CryptographicException or KeyNotFoundException or InvalidOperationException or ArgumentException)
        {throw new InvalidDataException("Invalid signed release metadata",e);}
    }
}
