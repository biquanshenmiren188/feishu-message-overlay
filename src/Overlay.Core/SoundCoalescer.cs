namespace Overlay.Core;
// A leading-edge cooldown: no queued playback, no timer, no message suppression.
public sealed class SoundCoalescer
{
    private long? last;
    public bool TryRequest(long monotonicMilliseconds)
    {
        if(last is {} previous && monotonicMilliseconds-previous<2000)return false;
        last=monotonicMilliseconds;return true;
    }
}
