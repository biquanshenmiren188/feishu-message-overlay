using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
namespace Overlay.App;
// Called only after a local user explicitly checks save and submits.
internal static class CredentialVault
{
    [StructLayout(LayoutKind.Sequential)] private struct Blob { public int Length; public IntPtr Data; }
    [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Unicode)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool CryptProtectData(ref Blob input, string description, IntPtr entropy, IntPtr reserved, IntPtr prompt, int flags, out Blob output);
    [DllImport("crypt32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool CryptUnprotectData(ref Blob input, IntPtr description, IntPtr entropy, IntPtr reserved, IntPtr prompt, int flags, out Blob output);
    [DllImport("kernel32.dll")] private static extern IntPtr LocalFree(IntPtr memory);
    private static string FileName => Path.Combine(LocalStorage.DirectoryPath,"application.dpapi");
    internal static string LoadState {get;private set;}="not_loaded";
    internal static byte[] TransformPublisherKey(byte[] data,bool encrypt)=>Transform(data,encrypt);
    private static byte[] Transform(byte[] data, bool encrypt)
    {
        var input = new Blob { Length = data.Length, Data = Marshal.AllocHGlobal(data.Length) }; Blob output = default;
        try
        {
            Marshal.Copy(data, 0, input.Data, data.Length);
            var success = encrypt ? CryptProtectData(ref input, "FeishuMessageOverlay application", IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 1, out output) : CryptUnprotectData(ref input, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 1, out output);
            if (!success) throw new CryptographicException();
            var result = new byte[output.Length]; Marshal.Copy(output.Data, result, 0, result.Length); return result;
        }
        finally
        {
            for (var i = 0; i < input.Length; i++) Marshal.WriteByte(input.Data, i, 0);
            Marshal.FreeHGlobal(input.Data);
            if (output.Data != IntPtr.Zero) { for (var i = 0; i < output.Length; i++) Marshal.WriteByte(output.Data, i, 0); LocalFree(output.Data); }
        }
    }
    public static bool Save(ConnectionSettings settings)
    {
        if (App.SmokeMode) return false;
        var plain = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { settings.AppId, settings.Secret }));
        try { var encrypted = Transform(plain, true); LocalStorage.AtomicWrite(FileName,encrypted);return true; }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or CryptographicException) { return false; }
        finally { CryptographicOperations.ZeroMemory(plain); }
    }
    public static ConnectionSettings? LoadOnUserRequest()
    {
        if (App.SmokeMode) return null;
        byte[]? plain = null;
        try { plain = Transform(File.ReadAllBytes(FileName), false); var stored = JsonSerializer.Deserialize<ConnectionSettings>(plain);LoadState=stored is null?"invalid_configuration":"loaded";return stored; }
        catch(FileNotFoundException){LoadState="missing";return null;}catch(DirectoryNotFoundException){LoadState="missing";return null;}
        catch(IOException){LoadState="io_error";return null;}catch(UnauthorizedAccessException){LoadState="access_denied";return null;}catch(CryptographicException){LoadState="decrypt_failed";return null;}catch(JsonException){LoadState="invalid_configuration";return null;}
        finally { if (plain is not null) CryptographicOperations.ZeroMemory(plain); }
    }
}
