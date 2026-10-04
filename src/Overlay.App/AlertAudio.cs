using System.IO;
using System.Media;
using System.Windows.Media;
using System.Runtime.InteropServices;
namespace Overlay.App;
internal sealed class AlertAudio : IDisposable
{
    private readonly MediaPlayer player=new();
    [DllImport("winmm.dll",EntryPoint="PlaySoundW",CharSet=CharSet.Unicode)] private static extern bool PlaySound(string? path,nint module,uint flags);
    [DllImport("winmm.dll")] private static extern uint waveOutGetNumDevs();
    internal static bool PlayWave(string path)=>IsSupported(path) && PlaySound(System.IO.Path.GetFullPath(path),0,0x20000|1|2);
    internal static bool HasOutputDevice=>waveOutGetNumDevs()>0;
    private string pathName="";
    public string PathName {get=>pathName;set=>pathName=LocalStorage.ResolveExistingFile(value);}
    internal bool? LastWaveAccepted {get;private set;}
    public static bool IsSupported(string path)
    {
        try
        {
            var file=new FileInfo(path);if(file.Length is <12 or >2097152) return false;
            using var input=File.OpenRead(path);var header=new byte[12];if(input.Read(header)!=12)return false;
            return (System.Text.Encoding.ASCII.GetString(header,0,4)=="RIFF" && System.Text.Encoding.ASCII.GetString(header,8,4)=="WAVE") ||
                (System.IO.Path.GetExtension(path).Equals(".mp3",StringComparison.OrdinalIgnoreCase) &&
                 (System.Text.Encoding.ASCII.GetString(header,0,3)=="ID3" || (header[0]==255 && (header[1]&224)==224)));
        }
        catch { return false; }
    }
    public void Play()
    {
        if(PathName.Length==0 || !IsSupported(PathName)){SystemSounds.Asterisk.Play();return;}
        if(System.IO.Path.GetExtension(PathName).Equals(".wav",StringComparison.OrdinalIgnoreCase)){LastWaveAccepted=PlayWave(PathName);if(LastWaveAccepted!=true)SystemSounds.Asterisk.Play();return;}
        try {player.Stop();player.Open(new Uri(System.IO.Path.GetFullPath(PathName)));player.Volume=1;player.Play();}
        catch {SystemSounds.Asterisk.Play();}
    }
    public void Dispose(){PlaySound(null,0,0);player.Close();}
}
