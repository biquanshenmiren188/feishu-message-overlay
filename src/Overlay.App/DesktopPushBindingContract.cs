using System.IO;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace Overlay.App;
public partial class MainWindow
{
    internal async Task RunPushCodeContractAsync(string directory)
    {
        if(!App.SmokeMode)throw new InvalidOperationException();
        var checks=new List<string>();void Check(bool ok,string name){if(!ok)throw new InvalidOperationException(name);checks.Add(name);}
        const string firstCode="12345678",secondCode="87654321";
        var path=Path.Combine(directory,"synthetic-code.dpapi");File.Delete(path);
        var binding=new DesktopPushBinding(path);var verified=0;
        Task Verify(string code){verified++;if(code=="11111111")throw new IOException("synthetic verification failure");return Task.CompletedTask;}
        Check(binding.Readable&&!binding.Bound&&binding.Code=="","missing binding defaults to receive all");
        await binding.ChangeAsync(firstCode,Verify);
        Check(binding.Bound&&new DesktopPushBinding(path).Code==firstCode,"encrypted binding survives restart");
        Check(!Encoding.UTF8.GetString(File.ReadAllBytes(path)).Contains(firstCode,StringComparison.Ordinal),"push code is not stored as plain text");
        try{await binding.ChangeAsync("11111111",Verify);}catch(IOException){}
        Check(binding.Code==firstCode&&new DesktopPushBinding(path).Code==firstCode,"failed verification preserves prior binding and disk");
        var failedStore=new DesktopPushBinding(path,(_,_)=>throw new IOException("synthetic disk failure"));
        Check(!await failedStore.ChangeAsync(secondCode,Verify)&&failedStore.Code==firstCode&&new DesktopPushBinding(path).Code==firstCode,"failed persistence preserves prior binding");
        await binding.ChangeAsync(secondCode,Verify);Check(new DesktopPushBinding(path).Code==secondCode,"successful switch persists second identity");
        var beforeUnbind=verified;await binding.ChangeAsync("",Verify);
        Check(!binding.Bound&&new DesktopPushBinding(path).Code==""&&verified==beforeUnbind,"explicit unbind works offline and persists all reception");
        File.WriteAllBytes(path,[1,2,3]);var corrupt=new DesktopPushBinding(path);
        Check(!corrupt.Readable&&corrupt.Code is null,"corrupt encrypted storage does not silently unbind");
        await corrupt.ChangeAsync("",Verify);Check(corrupt.Readable&&!corrupt.Bound,"explicit unbind can recover unreadable storage");
        var group=CloudMessageSource.GroupHash("oc_binding_fixture");var stamp=DateTimeOffset.UtcNow.AddMinutes(-1);
        object Message(string id)=>new{id=PublicWebPublisher.Digest(id),groupId=group,senderType="bot",sentAt=stamp,title="Synthetic binding fixture",body="Synthetic only",actions=System.Array.Empty<object>()};
        string State(string code,string id,bool includeProtocol=true)
        {
            var state=new Dictionary<string,object?>{{"cloudMode",true},{"sourceConnected",true},{"groups",new[]{new{id="oc_binding_fixture",groupId=group,name="Fixture"}}},{"messages",new[]{Message(id)}},{"pinned",null},{"pinnedGroupId",""},{"opportunities",null},
                {"desktopRules",new{revision=code==firstCode?1:2,messages=new{},cards=new{},desktopEnabled=true,cardsEnabled=true}}};
            if(includeProtocol)state["pushBinding"]=new{protocol=1,bound=code.Length>0,canManage=code.Length>0};return JsonSerializer.Serialize(state);
        }
        try{using var legacy=JsonDocument.Parse(State(firstCode,"old",false));DesktopPushBinding.ValidateState(legacy.RootElement,firstCode);throw new InvalidOperationException("legacy server was accepted");}catch(JsonException){checks.Add("old server without binding protocol rejected");}
        try{using var wrong=JsonDocument.Parse(State("","other"));DesktopPushBinding.ValidateState(wrong.RootElement,firstCode);throw new InvalidOperationException("wrong identity mode accepted");}catch(JsonException){checks.Add("unexpected unbound response rejected for bound client");}
        var pollCount=0;var failTransport=false;
        await using(var scoped=new CloudMessageSource(payload=>
        {
            var request=JsonSerializer.SerializeToElement(payload);if(request.GetProperty("pushCode").GetString()!=firstCode)throw new InvalidOperationException("state request selected wrong identity");Interlocked.Increment(ref pollCount);
            if(failTransport)throw new IOException("synthetic offline");return Task.FromResult(JsonDocument.Parse(State(firstCode,"bound")));
        },TimeSpan.FromMilliseconds(40),pushCode:firstCode))
        {
            await Until(()=>scoped.StateLoaded);
            Check(scoped.CanManage&&scoped.Rules.DesktopEnabled,"validated bound state enables only scoped management");
            Check(pollCount>0,"state request carries selected identity");
            failTransport=true;await Until(()=>!scoped.RulesConnected);
            Check(!scoped.CanManage&&!scoped.Rules.DesktopEnabled&&!scoped.Rules.CardsEnabled&&(await scoped.ReadAsync(CancellationToken.None)).Count==0,"transport failure blocks bound display sound and pending data");
        }
        pushBinding=new DesktopPushBinding(path);verifyPushBinding=Verify;
        var requestCodes=new List<string>();
        bindingSourceFactory=code=>new CloudMessageSource(payload=>
        {
            var sent=JsonSerializer.SerializeToElement(payload).GetProperty("pushCode").GetString()!;lock(requestCodes)requestCodes.Add(sent);
            return Task.FromResult(JsonDocument.Parse(State(code,code.Length==0?"all":code==firstCode?"person-a":"person-b")));
        },TimeSpan.FromMilliseconds(50),pushCode:code);
        await StartCloudAsync();await Until(()=>displayed.Count==1);
        Check(source is CloudMessageSource {CanManage:false}&&opportunityBoard.ManageRules is null,"unbound source receives all and disables editing");
        await ChangePushBindingAsync(firstCode);await Until(()=>displayed.LastOrDefault()?.Id==PublicWebPublisher.Digest("person-a"));
        Check(displayed.Count==1&&source is CloudMessageSource {CanManage:true}&&soundRequests==0,"binding replaces unbound history without replaying sound");
        var savedSource=source;await ChangePushBindingAsync("11111111");
        Check(ReferenceEquals(savedSource,source)&&pushBinding.Code==firstCode&&displayed.Count==1,"failed UI bind keeps running original source");
        var card=JsonSerializer.SerializeToElement(new{id="identity-stale-card",pair="identity-stale",validUntil=DateTimeOffset.UtcNow.AddHours(1)});
        opportunityBoard.Model.Cards["identity-stale"]=new OpportunityModel.Entry(card);opportunityBoard.Model.Sample=DateTimeOffset.UtcNow;
        await ChangePushBindingAsync(secondCode);await Until(()=>displayed.LastOrDefault()?.Id==PublicWebPublisher.Digest("person-b"));
        Check(displayed.Count==1&&opportunityBoard.Model.Cards.Count==0&&soundRequests==0,"switch clears previous messages pin cards and cached sample without sound");
        await ChangePushBindingAsync("");await Until(()=>displayed.LastOrDefault()?.Id==PublicWebPublisher.Digest("all"));
        Check(displayed.Count==1&&source is CloudMessageSource {CanManage:false}&&opportunityBoard.ManageRules is null,"unbind restores full reception and removes management");
        Check(requestCodes.Contains(firstCode)&&requestCodes.Contains(secondCode)&&requestCodes.Contains(""),"each replacement source requests its own scope");
        var workingFactory=bindingSourceFactory;
        bindingSourceFactory=code=>new CloudMessageSource(_=>throw new IOException("synthetic initial transport failure"),TimeSpan.FromMilliseconds(40),pushCode:code);
        await ChangePushBindingAsync(firstCode);await Until(()=>source is CloudMessageSource {State:LinkState.Reconnecting}&&Status.Text.Contains("已暂停接收",StringComparison.Ordinal));
        Check(source is CloudMessageSource {StateLoaded:false}&&displayed.Count==0,"first bound request failure displays paused status without waiting for initial state");
        bindingSourceFactory=workingFactory;await ChangePushBindingAsync("");await Until(()=>displayed.Count==1);
        // Hold an old poller's cancellation cleanup while two starts race.
        await StopAsync("synthetic lifecycle setup");
        var entered=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseOld=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        source=new CloudMessageSource(cancellableTransport:async(_,cancel)=>
        {entered.TrySetResult();try{await Task.Delay(Timeout.Infinite,cancel);}catch(OperationCanceledException){await releaseOld.Task;throw;}return JsonDocument.Parse("{}");});
        await entered.Task;
        var created=0;bindingSourceFactory=code=>{created++;return workingFactory!(code);};
        var firstStart=StartCloudAsync();await pushBinding.ChangeAsync(secondCode,Verify);
        var newestStart=StartCloudAsync();releaseOld.TrySetResult();await Task.WhenAll(firstStart,newestStart);
        await Until(()=>displayed.LastOrDefault()?.Id==PublicWebPublisher.Digest("person-b"));
        Check(created==1&&source is CloudMessageSource {CanManage:true}&&pushBinding.Code==secondCode,"concurrent starts retain only newest bound source without orphan poller");
        bindingSourceFactory=workingFactory;await ChangePushBindingAsync("");await Until(()=>displayed.Count==1);
        bindingSourceFactory=_=>throw new IOException("synthetic source initialization failure");
        await ChangePushBindingAsync(firstCode);
        Check(pushBinding.Code==firstCode&&new DesktopPushBinding(path).Code==firstCode&&PushBindingStatus.Text.Contains("已保存",StringComparison.Ordinal)&&source is null,"saved binding and reconnect failure reported accurately");
        bindingSourceFactory=workingFactory;await ChangePushBindingAsync("");await Until(()=>displayed.Count==1);
        var diagnosis=DiagnosticSnapshot();Check(!diagnosis.Contains(firstCode,StringComparison.Ordinal)&&!diagnosis.Contains(secondCode,StringComparison.Ordinal),"diagnostics contain no push code");
        UpdatePushBindingLabel();SettingsClick(this,new());settingsWindow!.Left=-12000;settingsWindow.Top=-12000;settingsWindow.UpdateLayout();
        Check(PushCodeInput.ActualWidth>200&&BindPushCode.ActualWidth>60&&UnbindPushCode.ActualWidth>80&&PushBindingStatus.Text.Contains("全部",StringComparison.Ordinal),"native settings binding controls visible with unbound feedback");
        var image=new RenderTargetBitmap((int)Math.Ceiling(settingsWindow.ActualWidth),(int)Math.Ceiling(settingsWindow.ActualHeight),96,96,PixelFormats.Pbgra32);image.Render(settingsWindow);var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(image));using(var file=File.Create(Path.Combine(directory,"push-code-settings.png")))encoder.Save(file);settingsWindow.Hide();
        await StopAsync("synthetic completed");File.WriteAllText(Path.Combine(directory,"push-code-contract.json"),JsonSerializer.Serialize(new{passed=true,checks=checks.Distinct().ToArray(),syntheticOnly=true,realCredentialUsed=false}));
        async Task Until(Func<bool> ready){for(var i=0;i<200&&!ready();i++)await Task.Delay(25);if(!ready())throw new InvalidOperationException("Binding contract timeout");await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);}
    }
}
