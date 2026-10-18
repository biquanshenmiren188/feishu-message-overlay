using System.IO;
namespace Overlay.App;
public partial class MainWindow
{
    private async Task RunLayoutReadingContractAsync(string output)
    {
        // The former shrink-to-three policy has been replaced by a full-height,
        // preferred-font viewport. Exercise the actual WPF layout and eviction.
        await RunFullHeightContractAsync(Path.Combine(output,"full-height-runtime.json"));
    }
}
