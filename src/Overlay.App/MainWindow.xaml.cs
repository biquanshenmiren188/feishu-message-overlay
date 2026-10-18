using System.ComponentModel;
using System.Collections.ObjectModel;
using System.Windows.Input;
using System.Windows.Controls.Primitives;
using System.Windows.Media.Animation;
using System.Media;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Overlay.Core;
using System.IO;
namespace Overlay.App;
public partial class MainWindow : Window
{
    private readonly MessageStore store = new(expireMessages:false);
    private readonly OpportunityBoard opportunityBoard=new();
    private readonly DispatcherTimer opportunityTimer=new(){Interval=TimeSpan.FromSeconds(1)};
    private readonly PublicWebPublisher webPublisher=new();
    private readonly TimedMessageReader reader=new();
    private readonly DispatcherTimer readingTimer=new();
    private readonly DispatcherTimer readingIdleTimer=new(){Interval=TimeSpan.FromSeconds(10)};
    private readonly DispatcherTimer preferenceTimer=new(){Interval=TimeSpan.FromMilliseconds(400)};
    private readonly DispatcherTimer expiryTimer=new(){Interval=TimeSpan.FromMinutes(1)};
    private Preferences lastPersisted=new();
    private Preferences? pendingPreferences;
    private Task preferenceSave=Task.CompletedTask;
    private long renderedRevision=-1;
    private int readScheduled;
    private ScrollViewer? scrollView;
    private ScrollViewer MessageScroll {get{MessageList.ApplyTemplate();return scrollView??=(ScrollViewer)MessageList.Template.FindName("PART_MessageScroll",MessageList);}}

    private readonly ObservableCollection<IncomingMessage> displayed = [];
    private IncomingMessage[] readingQueue=[];
    private long cloudConnectionRevision;
    private bool focusCloudLatest;
    private string? rangeStart;
    private string pinnedChatId="";private bool updatingPinnedChoice;
    private IncomingMessage? pinnedLatest;
    private HashSet<string> pinnedHoldChats=[];
    private bool followingPaused, synchronizingScroll;
    private bool verifyReadingTimer, initialFit=true, fittingWindow;
    private readonly DispatcherTimer scrollIdle = new() { Interval = TimeSpan.FromSeconds(1.4) };
    private readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromSeconds(1) };
    private readonly CancellationTokenSource shutdown = new();
    private IMessageSource? source;
    private bool ready, busy;
    private int generation;
    private HashSet<string> selectedChats = new(StringComparer.Ordinal);
    private LinkState? previousLinkState;
    private DateTimeOffset nextDemo;
    private int soundRequests;
    private string? trialReceipt;
    private string? trialTarget;
    private string? trialChat;
    private int realMessages;
    private string? lastMessageChatId;
    private string? lastAcceptedType;
    private readonly GroupReceptionStatistics reception=new();
    private bool lastReadable;
    private bool exiting;
    private Window? settingsWindow;
    private readonly AlertAudio audio=new();
    private readonly SoundCoalescer soundCoalescer=new();
    private DragYield? dragYield;
    private System.Windows.Forms.NotifyIcon? tray;
    public MainWindow()
    {
        InitializeComponent();
        OpportunityArea.Child=opportunityBoard;
        opportunityBoard.ColumnsChanged+=ResizeOpportunityColumns;
        opportunityBoard.ContentHeightChanged+=()=>RequestContentLayout();
        opportunityTimer.Tick+=(_,_)=>{if(source is CloudMessageSource cloud)opportunityBoard.Update(cloud.Opportunities,cloud.TransportConnected,DateTimeOffset.UtcNow,IsVisible);};
        var prefs = Preferences.Load();lastPersisted=prefs;reader.Configure(prefs.DwellSeconds,DateTimeOffset.UtcNow);DwellLabel.Text=reader.Seconds+"s";
        Width = double.IsFinite(prefs.Width) ? Math.Clamp(prefs.Width, 300, 1200) : 360;
        Height = double.IsFinite(prefs.Height) ? Math.Clamp(prefs.Height, 120, 1200) : 460;
        MessageList.ItemsSource=displayed; AutoScroll.IsChecked=prefs.AutoScroll;AutoJoined.IsChecked=prefs.AutoListenJoined;pinnedChatId=prefs.PinnedChatId;
        Pin.IsChecked = prefs.Topmost; Topmost = prefs.Topmost; Sound.IsChecked = prefs.Sound;
        FontChoice.ItemsSource = Fonts.SystemFontFamilies.OrderBy(f => f.Source).ToArray();
        FontChoice.SelectedItem = Fonts.SystemFontFamilies.FirstOrDefault(f => f.Source == prefs.Font) ?? Fonts.SystemFontFamilies.FirstOrDefault(f=>f.Source=="Segoe UI") ?? Fonts.SystemFontFamilies.First();
        FontScale.Value = double.IsFinite(prefs.FontSize) ? Math.Clamp(prefs.FontSize, 12, 32) : 16;
        MessageList.FontFamily = (FontFamily)FontChoice.SelectedItem; MessageList.FontSize = FontScale.Value;
        OpacityScale.Value=double.IsFinite(prefs.Opacity)?Math.Clamp(prefs.Opacity*100,60,100):96;
        SourceInitialized+=(_,_)=>{WindowAlpha.Set(this,OpacityScale.Value/100);dragYield=new DragYield(this,()=>Pin.IsChecked==true);}; OpacityLabel.Text=$"背景透明度 {OpacityScale.Value:0}%";
        audio.PathName=prefs.AudioPath; AudioLabel.Text=audio.PathName.Length==0?"系统提示音":Path.GetFileName(audio.PathName);
        Autostart.IsChecked=!App.SmokeMode && StartupRegistration.IsEnabled();
        CreateTray();
        PreviewMouseDown+=(_,_)=>dragYield?.OwnInput();PreviewKeyDown+=(_,_)=>dragYield?.OwnInput();PreviewMouseWheel+=(_,_)=>dragYield?.OwnInput();
        timer.Tick += async (_, _) => await ReadAsync();
        Loaded += (_, _) => {if(!App.SmokeMode)FitMessageViewport();PlaceTopRight();WindowAlpha.Set(this,OpacityScale.Value/100);};
        scrollIdle.Tick+=(_,_)=> {if(MessageBar.IsMouseOver || Mouse.Captured is Thumb)return;scrollIdle.Stop();MessageBar.BeginAnimation(OpacityProperty,new DoubleAnimation(0,TimeSpan.FromMilliseconds(180)));MessageBar.IsHitTestVisible=false;};
        SizeChanged += (_, e) => { if(ready && !fittingWindow && (e.WidthChanged || e.HeightChanged))RequestContentLayout(); if(ready)WindowAlpha.Set(this,OpacityScale.Value/100);if(ready && !fittingWindow && Mouse.LeftButton==MouseButtonState.Pressed){if(e.HeightChanged)initialFit=false;SavePreferences();} };
        MessageArea.PreviewMouseDown+=(_,_)=>PauseReading();
        PinnedArea.PreviewMouseDown+=(_,_)=>PauseReading();
        SystemParameters.StaticPropertyChanged+=WorkAreaChanged;
        Closed+=(_,_)=>SystemParameters.StaticPropertyChanged-=WorkAreaChanged;
        DpiChanged+=(_,_)=>RefitWorkArea();
        MessageBar.SetBinding(System.Windows.Controls.Primitives.RangeBase.MaximumProperty,new System.Windows.Data.Binding("ScrollableHeight"){Source=MessageScroll});
        MessageBar.SetBinding(System.Windows.Controls.Primitives.ScrollBar.ViewportSizeProperty,new System.Windows.Data.Binding("ViewportHeight"){Source=MessageScroll});
        readingTimer.Tick+=(_,_)=>ReadingTick();
        readingIdleTimer.Tick+=(_,_)=>{readingIdleTimer.Stop();if(!IsVisible || AutoScroll.IsChecked!=true || exiting)return;if(Mouse.Captured is Thumb){readingIdleTimer.Start();return;}followingPaused=false;FocusVisibleReading();ScheduleReading();};
        IsVisibleChanged+=(_,_)=>{readingIdleTimer.Stop();followingPaused=false;FocusVisibleReading();ScheduleReading();};
        preferenceTimer.Tick+=async(_,_)=>await FlushPreferencesAsync();
        expiryTimer.Tick+=(_,_)=>{store.Prune(DateTimeOffset.UtcNow);Render();};
        PinnedArea.SizeChanged+=(_,_)=>WindowAlpha.Set(this,OpacityScale.Value/100);
        ready = true;
    }
    private async Task StopAsync(string status)
    {
        generation++; timer.Stop(); opportunityTimer.Stop(); var old = source; source = null;
        opportunityBoard.Update(null,false,DateTimeOffset.UtcNow,IsVisible);
        pinnedHoldChats=!exiting && old is OfficialBotSource {State:LinkState.Connected or LinkState.Reconnecting}?new(selectedChats,StringComparer.Ordinal):[];
        selectedChats.Clear(); previousLinkState = null;
        store.Clear(DateTimeOffset.UtcNow); Render(); SetStatus(status);
        if (old is not null) await old.DisposeAsync();
    }
    private async void DemoClick(object sender, RoutedEventArgs e)
    {
        await StopAsync("模拟演示 · 非真实飞书消息");
        source = new DemoSource(); selectedChats.Add("demo"); nextDemo = DateTimeOffset.MinValue; store.Start(DateTimeOffset.UtcNow); timer.Start(); await ReadAsync();
    }
    private async Task ReadAsync()
    {
        if (busy || source is null) return;
        busy = true; var current = source; var version = generation;
        try
        {
            if (current is DemoSource && DateTimeOffset.UtcNow < nextDemo) { store.Prune(DateTimeOffset.UtcNow); Render(); return; }
            if (current is DemoSource) nextDemo = DateTimeOffset.UtcNow.AddSeconds(4);
            if (current is OfficialBotSource link)
            {
                if (previousLinkState != link.State)
                {
                    // A state transition discards stale display and establishes a fresh baseline.
                    // SDK reconnect keeps its dedup IDs and accepts only post-recovery events.
                    if (link.State is LinkState.Reconnecting or LinkState.Error or LinkState.Protected || previousLinkState == LinkState.Reconnecting)
                    { store.Clear(DateTimeOffset.UtcNow); Render(); }
                    previousLinkState = link.State;
                }
                SetStatus(link.Mode);
            }
            if(current is OfficialBotSource membership && AutoJoined.IsChecked==true && !selectedChats.SetEquals(membership.JoinedChatIds)){selectedChats=new(membership.JoinedChatIds,StringComparer.Ordinal);reception.Select(selectedChats);renderedRevision=-1;UpdatePinnedChoices();}
            var messages = await current.ReadAsync(shutdown.Token);
            if (version != generation || source != current || shutdown.IsCancellationRequested) return;
            if(current is CloudMessageSource opportunitySource)
                opportunityBoard.Update(opportunitySource.Opportunities,opportunitySource.TransportConnected,DateTimeOffset.UtcNow,IsVisible);
            var cloudPinAdded=false;
            if(current is CloudMessageSource {StateLoaded:true} cloud)
            {
                if(cloud.ConnectionRevision!=cloudConnectionRevision)
                {
                    cloudConnectionRevision=cloud.ConnectionRevision;
                    if(!followingPaused){focusCloudLatest=true;renderedRevision=-1;}
                }
                if(!selectedChats.SetEquals(cloud.Groups.Keys)){selectedChats=new(cloud.Groups.Keys,StringComparer.Ordinal);reception.Select(selectedChats);renderedRevision=-1;UpdatePinnedChoices();}
                if(pinnedChatId!=cloud.PinnedGroupId || pinnedLatest?.Id!=cloud.Pinned?.Id)
                {
                    cloudPinAdded=cloud.Pinned is { } newPin && newPin.SentAt>cloud.StartedAt;
                    pinnedChatId=cloud.PinnedGroupId;pinnedLatest=cloud.Pinned;renderedRevision=-1;UpdatePinnedChoices();
                }
                SetStatus(cloud.Mode);
            }
            var added = cloudPinAdded;var acceptedGroups=new HashSet<string>(StringComparer.Ordinal);
            foreach (var message in messages)
            {
                try {
                    if(selectedChats.Contains(message.SourceId) && store.Add(message,message.SourceId,DateTimeOffset.UtcNow,latestOnly:message.SourceId==pinnedChatId))
                    {
                        if(current is not CloudMessageSource cloudMessage || message.SentAt>cloudMessage.StartedAt)added=true;acceptedGroups.Add(message.SourceId);
                        if(current.IsRealConnection){realMessages++;lastMessageChatId=message.SourceId;lastAcceptedType=message.MessageType;lastReadable=message.Text.Length>0 && !message.Text.StartsWith("[该消息类型") && !message.Text.StartsWith("[正文格式") && !message.Text.StartsWith("[接口未提供");reception.RecordAccepted(message,true,lastReadable,DateTimeOffset.UtcNow);}
                    }
                }
                catch (ArgumentException) { /* malformed message: skip, never log content */ }
            }
            store.Prune(DateTimeOffset.UtcNow); Render();PublishWebState();
            var play=added && Sound.IsChecked==true && soundCoalescer.TryRequest(Environment.TickCount64);
            if(play){soundRequests++;if(!App.SmokeMode)audio.Play();}
            if(current.IsRealConnection && acceptedGroups.Count>0)reception.RecordSound(acceptedGroups,play,audio.LastWaveAccepted,Sound.IsChecked==true && !play);
        }
        catch (OperationCanceledException) { }
        catch (DedupCapacityException) { await StopAsync("保护暂停 · 最近消息过多，请重新连接；未重播历史消息"); }
        catch (Exception) { await StopAsync(current is OfficialBotSource failed ? failed.Mode : "读取失败 · 已停止并清空，未记录消息内容"); }
        finally { busy = false; }
    }
    internal void PaintPanelBackground(double value)
    {
        void Apply(Brush brush){if(OpportunityArea.Visibility==Visibility.Visible){Background=Brushes.Transparent;MessageBackdrop.Background=brush;MessageBackdrop.BorderBrush=Brushes.LightGray;MessageBackdrop.BorderThickness=new Thickness(.5);WindowFrame.BorderBrush=Brushes.Transparent;}else Background=brush;}
        var alpha=(byte)Math.Round(Math.Clamp(value,.6,1)*255);var white=Color.FromArgb(alpha,255,255,255);
        if(PinnedArea.Visibility!=Visibility.Visible || PinnedArea.ActualHeight<=0){Apply(new SolidColorBrush(white));return;}
        var height=Math.Max(1,ActualHeight>0?ActualHeight:Height);var top=Math.Clamp(28/height,0,1);var bottom=Math.Clamp((28+PinnedArea.ActualHeight)/height,top,1);
        var gray=Color.FromArgb(alpha,231,231,232);
        var fill=new LinearGradientBrush{StartPoint=new Point(0,0),EndPoint=new Point(0,1)};
        foreach(var stop in new[]{new GradientStop(white,0),new GradientStop(white,top),new GradientStop(gray,top),new GradientStop(gray,bottom),new GradientStop(white,bottom),new GradientStop(white,1)})fill.GradientStops.Add(stop);
        fill.Freeze();Apply(fill);
    }
    private void Render()
    {
        if(renderedRevision==store.Revision)return;renderedRevision=store.Revision;
        var items=store.Items;
        var pinnedAuthorized=selectedChats.Contains(pinnedChatId) || source is null && pinnedHoldChats.Contains(pinnedChatId);
        if(pinnedLatest?.SourceId!=pinnedChatId || !pinnedAuthorized)pinnedLatest=null;
        var candidate=items.Where(m=>m.SourceId==pinnedChatId).OrderByDescending(m=>m.SentAt).FirstOrDefault();
        if(pinnedAuthorized && candidate is not null && (pinnedLatest is null || candidate.SentAt>=pinnedLatest.SentAt))pinnedLatest=candidate;
        var pinned=pinnedLatest;
        if(PinnedCard.Content is not IncomingMessage shown || shown.Id!=pinned?.Id)PinnedCard.Content=pinned;
        PinnedArea.Visibility=pinned is null?Visibility.Collapsed:Visibility.Visible;
        WindowAlpha.Set(this,OpacityScale.Value/100);
        
        PinnedStatus.Text=pinnedChatId.Length==0?"未选择置顶群":!pinnedAuthorized?"该群当前不在已核实的监听列表，已暂停展示":pinned is null?"等待该群新消息（不读取历史）":"顶部仅保留该群最新一条";
        readingQueue=items.Where(m=>m.SourceId!=pinnedChatId && selectedChats.Contains(m.SourceId)).OrderBy(m=>m.SentAt).ToArray();
        reader.Synchronize(readingQueue.Select(m=>m.Id),DateTimeOffset.UtcNow);
        if(focusCloudLatest && readingQueue.Length>0)
        {
            focusCloudLatest=false;
            alignLatestAfterLayout=true;
        }
        if(rangeStart is null || !readingQueue.Any(m=>m.Id==rangeStart))rangeStart=reader.Current;
        DisplayRange(rangeStart,false);ScheduleReading();PublishWebState();
        RequestContentLayout();
        if(!App.SmokeMode){if(readingQueue.Length>0)expiryTimer.Start();else expiryTimer.Stop();}
    }
    private void PublishWebState()
    {
        if(source is OfficialBotSource {IsRealConnection:true})webPublisher.Update(true,selectedChats,pinnedChatId,store.Items,pinnedLatest);
        else if(source is not CloudMessageSource)webPublisher.Offline();
    }
    private void DisplayRange(string? id,bool resetScroll)
    {
        var start=Array.FindIndex(readingQueue,m=>m.Id==id);start=Math.Clamp(start,0,Math.Max(0,readingQueue.Length-1));
        rangeStart=readingQueue.ElementAtOrDefault(start)?.Id;
        // The store already bounds this history to 100. Let the viewport decide
        // how many messages are visible instead of reserving three slots.
        var target=readingQueue;
        if(displayed.Select(m=>m.Id).SequenceEqual(target.Select(m=>m.Id))){if(resetScroll)RequestContentLayout(id);return;}
        var anchor=displayed.FirstOrDefault(item=>MessageList.ItemContainerGenerator.ContainerFromItem(item) is FrameworkElement el && el.TranslatePoint(new Point(),MessageScroll).Y+el.ActualHeight>0);
        if(anchor is not null && MessageList.ItemContainerGenerator.ContainerFromItem(anchor) is FrameworkElement element)
            retainedReadingAnchor=(anchor.Id,element.TranslatePoint(new Point(),MessageScroll).Y);
        synchronizingScroll=true;
        for(var i=displayed.Count-1;i>=0;i--)if(!target.Any(m=>m.Id==displayed[i].Id))displayed.RemoveAt(i);
        for(var i=0;i<target.Length;i++)if(i>=displayed.Count || displayed[i].Id!=target[i].Id)displayed.Insert(i,target[i]);
        while(displayed.Count>target.Length)displayed.RemoveAt(displayed.Count-1);
        EmptyHint.Visibility=displayed.Count==0?Visibility.Visible:Visibility.Collapsed;
        RequestContentLayout(resetScroll?id:null);
        synchronizingScroll=false;
    }
    private void AutoScrollClick(object sender,RoutedEventArgs e)
    {
        readingIdleTimer.Stop();followingPaused=false;
        FocusVisibleReading();ScheduleReading();SavePreferences();
    }
    private void FocusVisibleReading()
    {
        var visible=displayed.FirstOrDefault(item=>MessageList.ItemContainerGenerator.ContainerFromItem(item) is FrameworkElement el && el.TranslatePoint(new Point(0,0),MessageScroll).Y+el.ActualHeight>0);
        reader.Focus(visible?.Id,DateTimeOffset.UtcNow);
    }
    private void ScheduleReading()
    {
        readingTimer.Stop();if(contentLayoutPending)return;if((App.SmokeMode && !verifyReadingTimer) || !ready || !IsVisible || followingPaused || AutoScroll.IsChecked!=true)return;
        if((reader.DelayUntilNext(DateTimeOffset.UtcNow)) is {} delay){readingTimer.Interval=TimeSpan.FromMilliseconds(Math.Max(50,delay.TotalMilliseconds));readingTimer.Start();}
    }
    private void ShowReadingMessage(string id)
    {DisplayRange(id,false);RequestContentLayout(id);}
    private void PauseReading()
    {
        if(AutoScroll.IsChecked!=true || !IsVisible || exiting)return;
        followingPaused=true;readingTimer.Stop();readingIdleTimer.Stop();readingIdleTimer.Start();
    }
    private void DwellClick(object sender,RoutedEventArgs e){DwellInput.Text=reader.Seconds.ToString();DwellPopup.IsOpen=true;DwellInput.Focus();DwellInput.SelectAll();}
    private void DwellKey(object sender,KeyEventArgs e){if(e.Key==Key.Enter){DwellCommit(sender,new());e.Handled=true;}}
    private void DwellCommit(object sender,RoutedEventArgs e)
    {if(!int.TryParse(DwellInput.Text,out var seconds) || seconds is <1 or >300){DwellInput.ToolTip="请输入1–300的整数秒";return;}readingIdleTimer.Stop();if(followingPaused){followingPaused=false;FocusVisibleReading();}reader.Configure(seconds,DateTimeOffset.UtcNow);DwellLabel.Text=seconds+"s";DwellPopup.IsOpen=false;ScheduleReading();SavePreferences();}
    private void ScheduleRead()
    {if(Interlocked.Exchange(ref readScheduled,1)!=0)return;Dispatcher.BeginInvoke(async()=>{Interlocked.Exchange(ref readScheduled,0);await ReadAsync();});}
    private void ShowScrollbar()
    {MessageBar.BeginAnimation(OpacityProperty,null);MessageBar.Opacity=1;MessageBar.IsHitTestVisible=MessageScroll.ScrollableHeight>0;scrollIdle.Stop();scrollIdle.Start();}
    private void MessageWheel(object sender,MouseWheelEventArgs e)
    {PauseReading();ShowScrollbar();}
    private void MessageKey(object sender,KeyEventArgs e)
    {if(e.Key is Key.Up or Key.Down or Key.PageUp or Key.PageDown or Key.Home or Key.End){PauseReading();ShowScrollbar();}}
    private void MessageMouseMove(object sender,MouseEventArgs e)
    {if(e.GetPosition(MessageArea).X>=MessageArea.ActualWidth-18)ShowScrollbar();}
    private void BarChanged(object sender,RoutedPropertyChangedEventArgs<double> e)
    {if(!ready || synchronizingScroll || !((MessageBar.IsMouseOver && Mouse.LeftButton==MouseButtonState.Pressed) || (Mouse.Captured is Thumb captured && MessageBar.IsAncestorOf(captured))))return;ShowScrollbar();PauseReading();MessageScroll.ScrollToVerticalOffset(e.NewValue);}
    private void MessageScrolled(object sender,ScrollChangedEventArgs e)
    {
        var prior=synchronizingScroll;synchronizingScroll=true;MessageBar.Value=MessageScroll.VerticalOffset;synchronizingScroll=prior;

    }
    private async void PauseClick(object sender, RoutedEventArgs e) => await StopAsync("已暂停 · 连接已关闭，消息已清空；可重新连接或演示");
    private void ClearClick(object sender, RoutedEventArgs e) { generation++; store.Clear(DateTimeOffset.UtcNow); Render(); }
    private async void ConnectClick(object sender, RoutedEventArgs e)
    {
        if(CloudMode.Enabled){await StartCloudAsync();return;}
        var dialog = new ConnectionWindow { Owner = this };
        if (dialog.ShowDialog() != true || dialog.Settings is not { } settings) return;
        await ConnectSettingsAsync(settings);
    }
    private async Task ConnectSettingsAsync(ConnectionSettings settings)
    {
        try
        {
            await StopAsync("连接中 · 正在启动官方连接器");
            var bridge = Path.Combine(AppContext.BaseDirectory, "bridge", "main.mjs");
            if (!File.Exists(bridge)) throw new FileNotFoundException();
            selectedChats = new(settings.ChatIds, StringComparer.Ordinal);reception.Select(settings.ChatIds);UpdatePinnedChoices(); store.Start(DateTimeOffset.UtcNow);
            source = await OfficialBotSource.StartAsync(ConnectionSettings.FindNode(), bridge, settings.AppId, settings.Secret, settings.ChatIds, settings.BotIds, shutdown.Token,autoJoined:AutoJoined.IsChecked==true);
            if(!ConnectionSelection.Save(settings))SetStatus("连接已启动 · 群选择保存失败，重启需重新配置");
            ((OfficialBotSource)source).Activity+=ScheduleRead;await ReadAsync();
        }
        catch (Exception) { await StopAsync("连接错误 · 请检查 Node运行时、桥接文件、应用配置及权限后重试"); }
        finally { settings.Secret = ""; }
    }
    private async void AutoJoinedClick(object sender,RoutedEventArgs e)
    {SavePreferences();await FlushPreferencesAsync();await RestoreConfiguredConnectionAsync();}
    private void SetStatus(string status)
    {
        if(Preferences.LoadState is not ("loaded" or "missing" or "not_loaded"))status+="；设置读取失败（"+Preferences.LoadState+"），原文件已保护";
        if(Status.Text==status)return;Status.Text=status;Title="飞书消息小窗";
        var linkState=(source as OfficialBotSource)?.State ?? (source as CloudMessageSource)?.State;
        var color=source?.IsRealConnection==true && linkState==LinkState.Connected && selectedChats.Count>0?"#07C983":
            linkState is LinkState.Error or LinkState.Protected?"#F07878":
            linkState is LinkState.Connecting or LinkState.Reconnecting || source is DemoSource?"#D5B35B":"#777777";
        var brush=(SolidColorBrush)new BrushConverter().ConvertFromString(color)!;brush.Freeze();State1.Fill=brush;State2.Fill=brush;State3.Fill=brush;
    }
    private async void RegistrationClick(object sender, RoutedEventArgs e) => await ShowRegistrationAsync(false);
    internal async Task ShowRegistrationAsync(bool autoBegin)
    {
        var dialog = new RegistrationWindow { Owner = this };
        if (autoBegin) dialog.Loaded += async (_, _) => await dialog.BeginAsync();
        if (dialog.ShowDialog() != true || dialog.Result is not { } credentials) return;
        var connection = new ConnectionWindow(credentials) { Owner = this };
        if (connection.ShowDialog() == true && connection.Settings is { } settings) await ConnectSettingsAsync(settings);
        credentials.Secret = "";
    }
    private void PreferenceChanged(object sender, RoutedEventArgs e) { if (!ready) return; Topmost = Pin.IsChecked == true; dragYield?.IntentChanged();SavePreferences(); }
    private void FontChanged(object sender, SelectionChangedEventArgs e) { if (!ready) return; if (FontChoice.SelectedItem is FontFamily family) MessageList.FontFamily = family; RequestContentLayout();SavePreferences(); }
    private void SizeChangedHandler(object sender, RoutedPropertyChangedEventArgs<double> e) { if (!ready) return; MessageList.FontSize = FontScale.Value;RequestContentLayout(); SavePreferences(); }
    private void SoundClick(object sender, RoutedEventArgs e) => audio.Play();
    private void PositionClick(object sender, RoutedEventArgs e) => PlaceTopRight();
    private Rect CurrentWorkArea()
    {
        var handle=new System.Windows.Interop.WindowInteropHelper(this).Handle;
        if(handle==0)return SystemParameters.WorkArea;
        var pixels=System.Windows.Forms.Screen.FromHandle(handle).WorkingArea;
        var matrix=System.Windows.PresentationSource.FromVisual(this)?.CompositionTarget?.TransformFromDevice??Matrix.Identity;
        return new Rect(matrix.Transform(new Point(pixels.Left,pixels.Top)),matrix.Transform(new Point(pixels.Right,pixels.Bottom)));
    }
    private void HomeClick(object sender,RoutedEventArgs e)
    {
        initialFit=true;var work=CurrentWorkArea();fittingWindow=true;
        var cardsWidth=OpportunityArea.Visibility==Visibility.Visible?CardsColumn.ActualWidth:0;
        Width=cardsWidth+Math.Clamp(Width-cardsWidth,300,Math.Max(300,Math.Min(680,work.Width-cardsWidth-16)));fittingWindow=false;
        Dispatcher.BeginInvoke(()=>{FitMessageViewport();PlaceTopRight();SavePreferences();},DispatcherPriority.Loaded);
    }
    private void FitMessageViewport() => MeasureContentHeight();
    private void WorkAreaChanged(object? sender,PropertyChangedEventArgs e)
    {if(e.PropertyName==nameof(SystemParameters.WorkArea))RefitWorkArea();}
    private void RefitWorkArea()
    {
        if(!ready || exiting || !initialFit)return;
        Dispatcher.BeginInvoke(()=>{if(exiting || !initialFit)return;lastFitKey=null;PlaceTopRight();RequestContentLayout();},DispatcherPriority.Loaded);
    }
    private void PlaceTopRight()
    {
        var work=CurrentWorkArea();fittingWindow=true;Width=Math.Min(Width,Math.Max(MinWidth,work.Width));Height=initialFit?Math.Max(MinHeight,work.Height):Math.Min(Height,Math.Max(MinHeight,work.Height));fittingWindow=false;
        WindowPlacement.TopRight(this);
    }
    private void SavePreferences()
    {
        if(App.SmokeMode && Preferences.ContractPath is null)return;
        if(Preferences.LoadState is not ("loaded" or "missing" or "not_loaded")){Status.Text=$"设置读取失败（{Preferences.LoadState}），原文件已保留；暂停保存";return;}
        var next=new Preferences{Width=Width,MessagePaneWidth=OpportunityArea.Visibility==Visibility.Visible?Math.Max(300,Width-CardsColumn.Width.Value):null,Height=Height,Topmost=Pin.IsChecked==true,Sound=Sound.IsChecked==true,Font=MessageList.FontFamily.Source,FontSize=FontScale.Value,Opacity=OpacityScale.Value/100,AutoScroll=AutoScroll.IsChecked==true,DwellSeconds=reader.Seconds,AudioPath=audio.PathName,AutoListenJoined=AutoJoined.IsChecked==true,PinnedChatId=pinnedChatId};
        if(next==lastPersisted && pendingPreferences is null)return;
        if(App.SmokeMode){if(next.Save())lastPersisted=next;return;}
        pendingPreferences=next;preferenceTimer.Stop();preferenceTimer.Start();
    }
    private async Task FlushPreferencesAsync()
    {
        preferenceTimer.Stop();var next=pendingPreferences;pendingPreferences=null;if(next is null)return;
        var previous=preferenceSave;var saving=Task.Run(async()=>{await previous;return next.Save();});preferenceSave=saving;
        if(await saving)lastPersisted=next;else {pendingPreferences??=next;Status.Text="设置保存失败，原文件已保留；请检查本机配置目录访问权限";}
    }
    internal bool FlushForSessionEnding()
    {
        SavePreferences();preferenceTimer.Stop();preferenceSave.GetAwaiter().GetResult();
        var next=pendingPreferences;if(next is null)return true;
        if(!next.Save()){Status.Text="设置保存失败，已阻止退出；原文件已保留";return false;}
        pendingPreferences=null;lastPersisted=next;return true;
    }
    internal async Task RunSmokeAsync(string output)
    {
        Directory.CreateDirectory(output);
        File.Delete(Path.Combine(output,"ui-assertion.txt"));
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
        void Assert(bool condition, [System.Runtime.CompilerServices.CallerArgumentExpression(nameof(condition))] string? test=null) { if (!condition) {File.WriteAllText(Path.Combine(output,"ui-assertion.txt"),test);throw new InvalidOperationException("UI smoke assertion failed");} }
        Assert(State1.Height==4 && State2.Height==8 && State3.Height==12 && State1.Width==3 && State2.Width==3 && State3.Width==3);
        Assert(State1.Parent is StackPanel signal && signal.Width==13 && signal.Height==12 && signal.ToolTip is not null);
        SetStatus("Synthetic disconnected");Assert(State1.Fill==State2.Fill && State2.Fill==State3.Fill && State1.Fill.ToString()=="#FF777777");
        Pin.IsChecked = false; PreferenceChanged(this, new()); Assert(!Topmost);
        Pin.IsChecked = true; PreferenceChanged(this, new()); Assert(Topmost);
        await RunYieldContractAsync(output);
        App.SmokeStage="ui";
        Width = 500; Height = 620; Assert(Width == 500 && Height == 620);
        FontScale.Value = 20; Assert(MessageList.FontSize == 20);
        FontChoice.SelectedItem = Fonts.SystemFontFamilies.First(f => f.Source == "Segoe UI");
        Assert(MessageList.FontFamily.Source == "Segoe UI");
        OpacityScale.Value=60;await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Render);UpdateLayout();
        File.WriteAllText(Path.Combine(output,"alpha-diagnostic.json"),System.Text.Json.JsonSerializer.Serialize(new {slider=OpacityScale.Value,alpha=WindowAlpha.Read(this),explicitSet=WindowAlpha.Set(this,.6),after=WindowAlpha.Read(this)}));
        Assert(WindowAlpha.Read(this)==153);OpacityScale.Value=100;await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Render);UpdateLayout();Assert(WindowAlpha.Read(this)==255);
        Preferences.ContractPath=Path.Combine(output,"appearance-contract.json");
        OpacityScale.Value=72;AutoScroll.IsChecked=false;AutoScrollClick(this,new());
        var restoredPrefs=Preferences.Load();Assert(Math.Abs(restoredPrefs.Opacity-.72)<.001 && !restoredPrefs.AutoScroll);
        var recoveredWindow=new MainWindow();recoveredWindow.Show();
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
        Assert(recoveredWindow.Opacity==1 && WindowAlpha.HasNativeLayered(recoveredWindow) && WindowAlpha.Read(recoveredWindow)==184 && recoveredWindow.AutoScroll.IsChecked==false);
        recoveredWindow.exiting=true;recoveredWindow.Close();recoveredWindow.audio.Dispose();Preferences.ContractPath=null;OpacityScale.Value=100;
        string? launched=null;var originalLauncher=MessageText.Launch;MessageText.Launch=uri=>launched=uri.AbsoluteUri;
        var url="https://example.com/notice?symbol=ABC&group=1&long="+new string('x',200);
        var textBlock=new TextBlock{TextWrapping=TextWrapping.Wrap};MessageText.SetContent(textBlock,"合成消息\n"+url);
        Assert(launched is null);var hyperlink=textBlock.Inlines.OfType<System.Windows.Documents.Hyperlink>().Single();
        hyperlink.RaiseEvent(new RoutedEventArgs(System.Windows.Documents.Hyperlink.ClickEvent));Assert(launched==url);
        var punctuation="https://example.com/a?query=%E4%B8%AD%E6%96%87&x=1";
        MessageText.SetContent(textBlock,"("+punctuation+")。中文后文\nhttps://example.com/path_(ok)，结束");
        var links=textBlock.Inlines.OfType<System.Windows.Documents.Hyperlink>().ToArray();Assert(links.Length==2);
        links[0].RaiseEvent(new RoutedEventArgs(System.Windows.Documents.Hyperlink.ClickEvent));Assert(launched==punctuation);
        links[1].RaiseEvent(new RoutedEventArgs(System.Windows.Documents.Hyperlink.ClickEvent));Assert(launched=="https://example.com/path_(ok)");
        Assert(new System.Windows.Documents.TextRange(textBlock.ContentStart,textBlock.ContentEnd).Text.Contains(")。中文后文"));
        Assert(!MessageText.Open("file:///C:/private") && !MessageText.Open("javascript:alert(1)"));MessageText.Launch=originalLauncher;
        App.SmokeStage="scroll_contract";Sound.IsChecked=false;AutoScroll.IsChecked=false;followingPaused=false;
        store.Start(DateTimeOffset.UtcNow.AddMinutes(-1));
        var scrollNow=DateTimeOffset.UtcNow;
        for(var i=0;i<30;i++)store.Add(new IncomingMessage("scroll-"+i,"demo","not visible",$"合成消息 {i}\n"+url,scrollNow.AddMilliseconds(i-100),SenderKind.Bot),"demo",scrollNow);
        Render();await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Loaded);UpdateLayout();MessageScroll.ScrollToVerticalOffset(100);
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Loaded);var held=MessageScroll.VerticalOffset;
        store.Add(new IncomingMessage("scroll-latest","demo","hidden","合成新消息",DateTimeOffset.UtcNow,SenderKind.Bot),"demo",DateTimeOffset.UtcNow);Render();
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Loaded);UpdateLayout();Assert(Math.Abs(MessageScroll.VerticalOffset-held)<1);
        AutoScroll.IsChecked=true;AutoScrollClick(this,new());await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Loaded);UpdateLayout();Assert(Math.Abs(MessageScroll.VerticalOffset-held)<2);
        MessageWheel(this,new MouseWheelEventArgs(Mouse.PrimaryDevice,0,120));MessageScroll.ScrollToVerticalOffset(100);
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Loaded);held=MessageScroll.VerticalOffset;
        store.Add(new IncomingMessage("scroll-read","demo","hidden","合成新消息 2",DateTimeOffset.UtcNow,SenderKind.Bot),"demo",DateTimeOffset.UtcNow);Render();
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Loaded);Assert(Math.Abs(MessageScroll.VerticalOffset-held)<1);
        AutoScroll.IsChecked=false;followingPaused=false;store.Start(DateTimeOffset.UtcNow.AddMinutes(-1));
        scrollNow=DateTimeOffset.UtcNow;
        for(var i=0;i<100;i++)store.Add(new IncomingMessage("capacity-"+i,"demo","hidden","合成消息\n"+url,scrollNow.AddMilliseconds(i-200),SenderKind.Bot),"demo",scrollNow);
        Render();await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Loaded);UpdateLayout();MessageScroll.ScrollToVerticalOffset(800);
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Loaded);UpdateLayout();
        var anchored=displayed.First(m=>MessageList.ItemContainerGenerator.ContainerFromItem(m) is FrameworkElement el && el.TranslatePoint(new Point(0,0),MessageScroll).Y+el.ActualHeight>0);
        var anchorY=((FrameworkElement)MessageList.ItemContainerGenerator.ContainerFromItem(anchored)).TranslatePoint(new Point(0,0),MessageScroll).Y;
        store.Add(new IncomingMessage("capacity-new","demo","hidden","合成新消息",DateTimeOffset.UtcNow,SenderKind.Bot),"demo",DateTimeOffset.UtcNow);Render();
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Loaded);UpdateLayout();
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();
        Assert(Math.Abs(((FrameworkElement)MessageList.ItemContainerGenerator.ContainerFromItem(anchored)).TranslatePoint(new Point(0,0),MessageScroll).Y-anchorY)<1);
        Assert(MessageScroll.Margin==new Thickness(0));
        var realized=displayed.Count(m=>MessageList.ItemContainerGenerator.ContainerFromItem(m) is not null);
        Assert(realized<40);
        var writesBefore=Preferences.WriteCount;var sample=System.Diagnostics.Stopwatch.StartNew();for(var i=0;i<100;i++)Render();sample.Stop();
        File.WriteAllText(Path.Combine(output,"light-performance.json"),System.Text.Json.JsonSerializer.Serialize(new{retained=displayed.Count,realized,unchangedRender100Milliseconds=sample.Elapsed.TotalMilliseconds,preferenceWriteDelta=Preferences.WriteCount-writesBefore}));
        Assert(MessageBar.Width==7);await Task.Delay(1800);await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Render);Assert(MessageBar.Opacity<.1 && !MessageBar.IsHitTestVisible);
        App.SmokeStage="real_dwell_timer";verifyReadingTimer=true;initialFit=false;readingIdleTimer.Stop();
        AutoScroll.IsChecked=true;followingPaused=false;reader.Configure(5,DateTimeOffset.UtcNow);
        reader.Focus(displayed[0].Id,DateTimeOffset.UtcNow);ShowReadingMessage(displayed[0].Id);
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Loaded);ScheduleReading();
        double ItemY(string id)
        {
            var item=displayed.First(m=>m.Id==id);
            return MessageList.ItemContainerGenerator.ContainerFromItem(item) is FrameworkElement element?element.TranslatePoint(new Point(0,0),MessageScroll).Y:double.NaN;
        }
        var timeline=new List<object>();
        for(var cycle=0;cycle<4;cycle++)
        {
            var beforeOffset=MessageScroll.VerticalOffset;var targetId=displayed[cycle].Id;var beforeTargetY=ItemY(targetId);
            if(cycle>0)await Task.Delay(5200);
            await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
            var targetY=ItemY(targetId);
            Assert(reader.Current==targetId && !followingPaused && readingTimer.IsEnabled);
            Assert(double.IsFinite(targetY) && Math.Abs(targetY)<1);
            if(cycle>0)Assert(beforeTargetY>1 && MessageScroll.VerticalOffset-beforeOffset>1);
            timeline.Add(new{cycle,current=reader.Current,at=DateTimeOffset.UtcNow,beforeOffset,beforeTargetY,offset=MessageScroll.VerticalOffset,targetY,extent=MessageScroll.ExtentHeight,viewport=MessageScroll.ViewportHeight,paused=followingPaused,timer=readingTimer.IsEnabled});
        }
        Assert(timeline.Count==4);
        reader.Configure(15,DateTimeOffset.UtcNow);ScheduleReading();
        var longTimeline=new List<object>();
        for(var cycle=0;cycle<2;cycle++)
        {
            var beforeId=reader.Current;var nextId=displayed[displayed.ToList().FindIndex(m=>m.Id==beforeId)+1].Id;
            var began=DateTimeOffset.UtcNow;var initialOffset=MessageScroll.VerticalOffset;
            var beforeAdvanceOffset=initialOffset;var beforeAdvanceTargetY=ItemY(nextId);
            if(cycle==0)
            {
                await Task.Delay(5000);
                var heldItem=displayed.First(m=>m.Id==beforeId);var heldY=((FrameworkElement)MessageList.ItemContainerGenerator.ContainerFromItem(heldItem)).TranslatePoint(new Point(0,0),MessageScroll).Y;
                store.Add(new IncomingMessage("arrival-during-dwell","demo","hidden","合成到达，不打断当前停留。",DateTimeOffset.UtcNow,SenderKind.Bot),"demo",DateTimeOffset.UtcNow);Render();
                await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);Assert(reader.Current==beforeId && readingTimer.IsEnabled && !followingPaused);
                Assert(Math.Abs(((FrameworkElement)MessageList.ItemContainerGenerator.ContainerFromItem(heldItem)).TranslatePoint(new Point(0,0),MessageScroll).Y-heldY)<1);
                beforeAdvanceOffset=MessageScroll.VerticalOffset;beforeAdvanceTargetY=ItemY(nextId);
                await Task.Delay(10200);
            }
            else await Task.Delay(15200);
            await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
            var targetY=ItemY(nextId);
            Assert(reader.Current==nextId && readingTimer.IsEnabled && !followingPaused);
            Assert(double.IsFinite(beforeAdvanceTargetY) && beforeAdvanceTargetY>1 && double.IsFinite(targetY) && Math.Abs(targetY)<1);
            Assert(MessageScroll.VerticalOffset-beforeAdvanceOffset>1);
            longTimeline.Add(new{cycle,from=beforeId,current=reader.Current,began,at=DateTimeOffset.UtcNow,initialOffset,beforeAdvanceOffset,beforeAdvanceTargetY,offset=MessageScroll.VerticalOffset,targetY,visualAdvance=beforeAdvanceTargetY-targetY,extent=MessageScroll.ExtentHeight,viewport=MessageScroll.ViewportHeight});
        }
        reader.Configure(2,DateTimeOffset.UtcNow);ScheduleReading();
        MessageWheel(this,new MouseWheelEventArgs(Mouse.PrimaryDevice,0,120));
        Assert(AutoScroll.IsChecked==true && followingPaused && !readingTimer.IsEnabled && readingIdleTimer.IsEnabled);
        var idleTimeline=new List<object>();var heldId=reader.Current;var heldOffset=MessageScroll.VerticalOffset;
        await Task.Delay(9100);Assert(reader.Current==heldId && followingPaused && Math.Abs(MessageScroll.VerticalOffset-heldOffset)<1);
        idleTimeline.Add(new{phase="nineSeconds",at=DateTimeOffset.UtcNow,current=reader.Current,offset=MessageScroll.VerticalOffset,followingPaused});
        await Task.Delay(1200);Assert(!followingPaused && reader.Current==heldId && readingTimer.IsEnabled);
        idleTimeline.Add(new{phase="resumedFullDwell",at=DateTimeOffset.UtcNow,current=reader.Current,offset=MessageScroll.VerticalOffset,followingPaused});
        await Task.Delay(2000);await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
        Assert(reader.Current!=heldId && MessageScroll.VerticalOffset>heldOffset+1);
        idleTimeline.Add(new{phase="advancedAfterFullDwell",at=DateTimeOffset.UtcNow,current=reader.Current,offset=MessageScroll.VerticalOffset,followingPaused});
        MessageWheel(this,new MouseWheelEventArgs(Mouse.PrimaryDevice,0,120));heldId=reader.Current;
        await Task.Delay(5000);MessageWheel(this,new MouseWheelEventArgs(Mouse.PrimaryDevice,0,120));
        await Task.Delay(5500);Assert(followingPaused && reader.Current==heldId);
        await Task.Delay(4800);Assert(!followingPaused && reader.Current==heldId);
        MessageWheel(this,new MouseWheelEventArgs(Mouse.PrimaryDevice,0,120));AutoScroll.IsChecked=false;AutoScrollClick(this,new());
        var stopped=reader.Current;await Task.Delay(10300);Assert(reader.Current==stopped && !readingTimer.IsEnabled && !readingIdleTimer.IsEnabled);
        AutoScroll.IsChecked=true;AutoScrollClick(this,new());MessageWheel(this,new MouseWheelEventArgs(Mouse.PrimaryDevice,0,120));
        Hide();Assert(!readingIdleTimer.IsEnabled && !readingTimer.IsEnabled);Show();Assert(!followingPaused && readingTimer.IsEnabled);
        File.WriteAllText(Path.Combine(output,"timed-reading-runtime.json"),System.Text.Json.JsonSerializer.Serialize(new{timeline,longTimeline,idleTimeline,repeatedInputExtendsDeadline=true,offCancelsResume=true,hideCancelsTimers=true,arrivalDoesNotInterrupt=true}));
        AutoScroll.IsChecked=true;followingPaused=false;reader.Focus(displayed.Last().Id,DateTimeOffset.UtcNow);ScheduleReading();Assert(!readingTimer.IsEnabled);
        verifyReadingTimer=false;readingTimer.Stop();
        File.WriteAllText(Path.Combine(output,"minimal-ui-contract.txt"),"PASS background-only per-pixel layered HWND style, Window.Opacity=1 and rendered background pixel alpha 153/184/255; Preferences.Save/Load and recreated HWND restore; capacity eviction preserves surviving reading anchor; full safe HTTP(S) hyperlink click capture without network; file/javascript rejected; no binding auto launch; follow on/off and manual reading position; 7 DIP overlay scrollbar idle fade. 150% images are layout render simulations.");
        await StopAsync("未连接");App.SmokeStage="ui";
        MessageText.SetContent(textBlock,"第一行\nhttps://example.com/test?q=1\n第三行");
        Assert(textBlock.Inlines.OfType<System.Windows.Documents.Hyperlink>().Single().FontWeight==FontWeights.Bold);
        Assert(textBlock.Inlines.OfType<System.Windows.Documents.Run>().Last().FontWeight==FontWeights.Normal);
        MessageText.SetContent(textBlock,"\n第二行\n第三行");Assert(textBlock.Inlines.OfType<System.Windows.Documents.Run>().Last().FontWeight==FontWeights.Normal);
        File.WriteAllText(Path.Combine(output,"font-availability.json"),System.Text.Json.JsonSerializer.Serialize(new{microsoftYaHeiInstalled=Fonts.SystemFontFamilies.Any(f=>f.Source=="Microsoft YaHei")}));
        var unchanged=Preferences.WriteCount;var revision=renderedRevision;Render();Assert(renderedRevision==revision && Preferences.WriteCount==unchanged);
        HomeClick(this,new());Assert(Left>=CurrentWorkArea().Left && Top>=CurrentWorkArea().Top);
        Assert(!ShowInTaskbar);Close();Assert(!IsVisible && source is null);Restore();Assert(IsVisible);
        Autostart.IsChecked=true;StartupClick(this,new());Assert(Autostart.IsChecked==false);
        Sound.IsChecked = false;
        await StopAsync("模拟演示 · 非真实飞书消息"); source = new DemoSource(); selectedChats.Add("demo"); nextDemo = DateTimeOffset.MinValue; store.Start(DateTimeOffset.UtcNow);
        await ReadAsync(); Assert(store.Items.Count == 1 && EmptyHint.Visibility == Visibility.Collapsed);
        Width=360;Height=460;FontScale.Value=14;
        store.Add(new IncomingMessage("visual-link","demo","hidden","合成演示消息：链接可点击并完整换行。\nhttps://example.com/notice?symbol=DEMO&detail="+new string('x',100),DateTimeOffset.UtcNow,SenderKind.Bot),"demo",DateTimeOffset.UtcNow);Render();
        store.Add(new IncomingMessage("visual-third","demo","hidden","第三条合成消息\n正文前两行加粗\n其余文字正常；时间贴首行。",DateTimeOffset.UtcNow,SenderKind.Bot),"demo",DateTimeOffset.UtcNow);Render();
        FontChoice.SelectedItem=Fonts.SystemFontFamilies.FirstOrDefault(f=>f.Source=="Microsoft YaHei") ?? Fonts.SystemFontFamilies.First(f=>f.Source=="Segoe UI");
        var alphaChecks=new List<object>();
        foreach(var percent in new[]{60,93,95,100})
        {
            OpacityScale.Value=percent;await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.Render);UpdateLayout();
            var sampleImage=new RenderTargetBitmap((int)ActualWidth,(int)ActualHeight,96,96,PixelFormats.Pbgra32);sampleImage.Render(this);
            var alphaPng=new PngBitmapEncoder();alphaPng.Frames.Add(BitmapFrame.Create(sampleImage));using(var alphaFile=File.Create(Path.Combine(output,$"background-{percent}.png")))alphaPng.Save(alphaFile);
            var bytes=new byte[(int)ActualWidth*(int)ActualHeight*4];sampleImage.CopyPixels(bytes,(int)ActualWidth*4,0);
            var opaqueBlack=0;for(var i=0;i<bytes.Length;i+=4)if(bytes[i+3]==255 && bytes[i]<25 && bytes[i+1]<25 && bytes[i+2]<25)opaqueBlack++;
            Assert(Opacity==1 && opaqueBlack>50 && Math.Abs(WindowAlpha.Read(this)!.Value-Math.Round(percent*2.55))<=1);
            alphaChecks.Add(new{percent,windowOpacity=Opacity,backgroundAlpha=WindowAlpha.Read(this),opaqueBlackPixels=opaqueBlack});
        }
        File.WriteAllText(Path.Combine(output,"background-only-alpha.json"),System.Text.Json.JsonSerializer.Serialize(alphaChecks));
        PlaceTopRight();await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
        var placement=System.Text.Json.JsonSerializer.SerializeToElement(WindowPlacement.Snapshot(this));
        Assert(placement.GetProperty("rightMargin").GetInt32()==0 && placement.GetProperty("topMargin").GetInt32()==0);
        File.WriteAllText(Path.Combine(output,"zero-gap-placement.json"),placement.GetRawText());
        reader.Configure(15,DateTimeOffset.UtcNow);DwellLabel.Text="15s";AutoScroll.IsChecked=true;FitMessageViewport();
        await Dispatcher.InvokeAsync(() => { }, DispatcherPriority.Render);
        UpdateLayout();
        var image = new RenderTargetBitmap((int)ActualWidth, (int)ActualHeight, 96, 96, PixelFormats.Pbgra32);
        image.Render(this); var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(image));
        using (var stream = File.Create(Path.Combine(output, "demo-window.png"))) encoder.Save(stream);
        var scaled=new RenderTargetBitmap((int)(ActualWidth*1.5),(int)(ActualHeight*1.5),144,144,PixelFormats.Pbgra32);scaled.Render(this);var scaledPng=new PngBitmapEncoder();scaledPng.Frames.Add(BitmapFrame.Create(scaled));using(var file=File.Create(Path.Combine(output,"demo-render-150.png")))scaledPng.Save(file);
        ClearClick(this, new()); Assert(store.Items.Count == 0);
        await StopAsync("已暂停"); Assert(source is null && store.Items.Count == 0);
        Assert(ConnectionSettings.Validate("cli_synthetic", "synthetic-only", ["oc_selected"], []) is null);
        Assert(ConnectionSettings.Validate("cli_synthetic", "synthetic-only", ["群名称"], []) is not null);
        var bridge = Path.Combine(AppContext.BaseDirectory, "bridge", "contract-fixture.mjs");
        selectedChats.Add("oc_selected"); store.Start(DateTimeOffset.UtcNow); Sound.IsChecked = true;
        App.SmokeStage = "pipe_start";
        source = await OfficialBotSource.StartAsync(ConnectionSettings.FindNode(), bridge, "cli_synthetic", "synthetic-only", ["oc_selected"], [], shutdown.Token, fixture: true);
        var link = (OfficialBotSource)source;
        for (var attempt = 0; attempt < 100 && link.State != LinkState.Connected; attempt++) await Task.Delay(25);
        Assert(link.State == LinkState.Connected && !link.IsRealConnection);
        App.SmokeStage = "first_delivery";
        await Task.Delay(30);
        await ReadAsync(); Assert(store.Items.Count == 1 && soundRequests == 1); // duplicate fixture delivered twice
        await ReadAsync(); Assert(soundRequests == 1);
        Sound.IsChecked=false;PreferenceChanged(this,new());Sound.IsChecked=true;PreferenceChanged(this,new());
        await ReadAsync();Assert(soundRequests==1); // toggling on must not replay existing alerts
        await link.ContractCommandAsync("reconnect");
        App.SmokeStage = "reconnecting";
        for (var attempt = 0; attempt < 100 && link.State != LinkState.Reconnecting; attempt++) await Task.Delay(10);
        Assert(link.State == LinkState.Reconnecting); await ReadAsync(); Assert(store.Items.Count == 0);
        App.SmokeStage = "reconnected_no_replay";
        for (var attempt = 0; attempt < 100 && link.State != LinkState.Connected; attempt++) await Task.Delay(10);
        Assert(link.State == LinkState.Connected); await ReadAsync(); Assert(store.Items.Count == 0 && soundRequests == 1);
        await link.ContractCommandAsync("fail");
        App.SmokeStage = "failure_disposal";
        for (var attempt = 0; attempt < 100 && link.State != LinkState.Error; attempt++) await Task.Delay(10);
        await ReadAsync(); Assert(source is null && store.Items.Count == 0 && OfficialBotSource.ActiveChildren == 0);
        File.WriteAllText(Path.Combine(output, "bridge-contract.txt"), "PASS private IPC, synthetic connection states, bot delivery, duplicate alarm suppression, reconnect baseline, error clears display, subprocess disposal. No real credentials or network.");
        async Task CaptureBlank(Window window, string name)
        {
            window.Show(); await Dispatcher.InvokeAsync(() => { }, DispatcherPriority.Render); window.UpdateLayout();
            var preview = new RenderTargetBitmap((int)window.ActualWidth, (int)window.ActualHeight, 96, 96, PixelFormats.Pbgra32);
            preview.Render(window); var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(preview));
            using (var file = File.Create(Path.Combine(output, name))) png.Save(file);
            var enlarged = new RenderTargetBitmap((int)(window.ActualWidth*1.5),(int)(window.ActualHeight*1.5),144,144,PixelFormats.Pbgra32);
            enlarged.Render(window);var high=new PngBitmapEncoder();high.Frames.Add(BitmapFrame.Create(enlarged));
            using(var file=File.Create(Path.Combine(output,Path.GetFileNameWithoutExtension(name)+"-150.png")))high.Save(file);
            window.Close();
        }
        await CaptureBlank(new ConnectionWindow(), "connection-empty.png");
        await CaptureBlank(new RegistrationWindow(), "registration-empty.png");
        await StopAsync("未连接 · 真实接入尚未验证");Sound.IsChecked=false;OpacityScale.Value=96;
        await CaptureBlank(this,"overlay-empty-100.png");Restore();
        SettingsClick(this,new());Assert(settingsWindow?.Opacity==1);
        await CaptureBlank(settingsWindow!,"settings-empty-100.png");settingsWindow!.Hide();
        CreateTray(verify:true);Assert(tray?.Visible==true);Close();Close();Assert(!IsVisible && tray?.Visible==true);Restore();Assert(IsVisible);
        File.WriteAllText(Path.Combine(output,"lifecycle-contract.txt"),"PASS taskbar hidden, X/repeated close hides, restore, opacity 60-100, settings remain opaque, startup failure rollback without registry writes. Physical tray clicks/session shutdown/multi-monitor DPI remain unverified.");
    }
    internal async Task BeginAuthorizedTrialAsync(string target,string receipt)
    {
        if(App.SmokeMode)return;trialReceipt=receipt;trialTarget=target;
        SetStatus("核实授权首群 · 仅查询准确群身份");WriteTrialReceipt();
        var credentials=CredentialVault.LoadOnUserRequest();
        if(credentials is null){SetStatus("本地加密配置不可用 · 未连接");WriteTrialReceipt();return;}
        var found=await GroupDiscovery.FindAsync(credentials,target);
        if(found.State!="matched"||found.ChatId is null){SetStatus("首群核验失败 · "+found.State+" / code="+found.Code);WriteTrialReceipt();return;}
        trialChat=found.ChatId;credentials=CredentialVault.LoadOnUserRequest();
        if(credentials is null){SetStatus("本地配置不可用");WriteTrialReceipt();return;}
        Sound.IsChecked=true;SavePreferences();
        await ConnectSettingsAsync(new ConnectionSettings{AppId=credentials.AppId,Secret=credentials.Secret,ChatIds=[trialChat]});credentials.Secret="";
        WriteTrialReceipt();
    }
    private async Task StartCloudAsync()
    {
        await StopAsync("Connecting to cloud source");
        cloudConnectionRevision=0;focusCloudLatest=false;
        AutoJoined.IsChecked=true;AutoJoined.IsEnabled=false;
        EnableOpportunityBoard();
        store.Start(DateTimeOffset.UtcNow.AddMinutes(-30));
        var cloud=new CloudMessageSource();source=cloud;cloud.Activity+=ScheduleRead;opportunityTimer.Start();await ReadAsync();
    }
    private void EnableOpportunityBoard()
    {
        if(OpportunityArea.Visibility==Visibility.Visible)return;
        OpportunityArea.Visibility=Visibility.Visible;MessagesColumn.Width=new GridLength(1,GridUnitType.Star);
        var work=CurrentWorkArea();var cardWidth=OpportunityColumnsPanel.CardWidth;
        CardsColumn.Width=new GridLength(cardWidth);
        // Reopening an already combined layout must not add the card pane twice.
        var textWidth=lastPersisted.CloudTextWidth(Width,300);
        fittingWindow=true;
        try{MinWidth=cardWidth+300;Width=Math.Min(cardWidth+textWidth,Math.Max(MinWidth,work.Width-16));}
        finally{fittingWindow=false;}
        opportunityBoard.MaximumColumns=Math.Max(1,(int)((work.Width-textWidth-2)/cardWidth));
        opportunityBoard.RefreshColumnLayout();
        RequestContentLayout();WindowAlpha.Set(this,OpacityScale.Value/100);PlaceTopRight();
    }
    private void ResizeOpportunityColumns(int count)
    {
        if(OpportunityArea.Visibility!=Visibility.Visible || exiting)return;
        var work=CurrentWorkArea();
        var textWidth=Math.Max(300,Width-CardsColumn.Width.Value);
        var maximum=Math.Max(1,(int)((work.Width-textWidth-2)/OpportunityColumnsPanel.CardWidth));
        opportunityBoard.MaximumColumns=maximum;
        var cardWidth=Math.Min(count,maximum)*OpportunityColumnsPanel.CardWidth;
        if(Math.Abs(CardsColumn.Width.Value-cardWidth)<.1)return;
        var right=Left+Width;fittingWindow=true;
        try{CardsColumn.Width=new GridLength(cardWidth);MinWidth=cardWidth+300;Width=cardWidth+textWidth;Left=Math.Max(work.Left,right-Width);}
        finally{fittingWindow=false;}
        opportunityBoard.RefreshColumnLayout();SavePreferences();
    }
    internal async Task RestoreConfiguredConnectionAsync()
    {
        if(CloudMode.Enabled){await StartCloudAsync();return;}
        ConnectionSelection? selected=null;ConnectionSettings? credentials=null;
        for(var attempt=0;attempt<6;attempt++)
        {
            selected=ConnectionSelection.Load();credentials=CredentialVault.LoadOnUserRequest();
            if(selected is not null && credentials is not null)break;
            if(credentials is not null){credentials.Secret="";credentials=null;}
            if(ConnectionSelection.LoadState=="missing" && CredentialVault.LoadState=="missing" && !StartupRegistration.IsEnabled())break;
            await Task.Delay(500);
        }
        if(selected is null){SetStatus($"启动读取群配置失败（{ConnectionSelection.LoadState}）；原配置已保留，可稍后重新加载");return;}
        if(credentials is null||credentials.AppId!=selected.AppId){if(credentials is not null)credentials.Secret="";SetStatus($"启动读取安全凭证失败（{CredentialVault.LoadState}）；无需重建应用，请重新加载已保存配置");return;}
        if(Preferences.LoadState is not ("loaded" or "missing")){credentials.Secret="";SetStatus($"设置读取失败（{Preferences.LoadState}），原文件已保留并暂停保存；请重新启动重试");return;}
        await ConnectSettingsAsync(new ConnectionSettings{AppId=credentials.AppId,Secret=credentials.Secret,ChatIds=selected.ChatIds,BotIds=selected.BotIds});credentials.Secret="";
    }
    internal void ObserveConfiguredState(string receipt)
    {trialReceipt=receipt;trialChat=ConnectionSelection.Load()?.ChatIds.FirstOrDefault();WriteTrialReceipt();}
    private void WriteTrialReceipt(){ } // Legacy startup option never writes a periodic receipt.
    internal string DiagnosticSnapshot()=>System.Text.Json.JsonSerializer.Serialize(new{updateVersion=DesktopAutoUpdate.CurrentVersion,automaticUpdates=desktopUpdates?.Enabled,updateStatus=desktopUpdates?.Status,opportunityCount=opportunityBoard.Model.Cards.Count,opportunityColumns=opportunityBoard.ColumnCount,opportunityPaneWidth=OpportunityArea.ActualWidth,opportunityPaneHeight=OpportunityArea.ActualHeight,activeOpportunities=opportunityBoard.ActiveCount,opportunityPaneVisible=OpportunityArea.Visibility==Visibility.Visible,opportunitySourceConnected=opportunityBoard.Model.Connected,webPublisherState=webPublisher.State,webPublisherHttp=webPublisher.LastHttp,webPublisherBatches=webPublisher.SuccessfulBatches,webPublishedMessages=webPublisher.AcknowledgedMessages,webPublisherLastSuccess=webPublisher.LastSuccess,webRemoteNormalCount=webPublisher.RemoteNormalCount,webRemotePinned=webPublisher.RemotePinned,weixinEnabled=false,weixinState="uninstalled",weixinSent=0,weixinFailed=0,state=((source as OfficialBotSource)?.State ?? (source as CloudMessageSource)?.State)?.ToString()??"NotConnected",cloudSource=source is CloudMessageSource,configuredChatIds=selectedChats.Order(StringComparer.Ordinal).ToArray(),lastMessageChatId,lastMessageType=lastAcceptedType,groupStats=reception.Snapshot(),realBotMessages=realMessages,cardMetadata=(source as OfficialBotSource)?.LastCardMetadata,cardDetailFailure=(source as OfficialBotSource)?.LastCardDetailsFailure,soundRequests,soundEnabled=Sound.IsChecked==true,lastWaveAccepted=audio.LastWaveAccepted,opacity=Opacity,backgroundOpacity=OpacityScale.Value/100,followingPaused,isVisible=IsVisible,readingIndex=Array.FindIndex(readingQueue,m=>m.Id==reader.Current),historyRetention="session_latest_100",messageCount=readingQueue.Length,visibleContainers=displayed.Count,viewportMessageCount=ViewportMessageCount(),messageDisplayMode="continuous_full_height",visibleStructuredCards=displayed.Count(m=>m.Card is not null),visibleCardButtons=displayed.Sum(m=>m.Card?.Buttons.Count??0),visibleSafeCardButtons=displayed.Sum(m=>m.Card?.Buttons.Count(b=>MessageCardParser.SafeUrl(b.Url))??0),pinnedStructuredCard=pinnedLatest?.Card is not null,pinnedVisible=PinnedCard.Content is not null,pinnedConfigured=pinnedChatId.Length>0,rangeStartIndex=Array.FindIndex(readingQueue,m=>m.Id==rangeStart),preferenceState=Preferences.LoadState,audioConfigured=audio.PathName.Length>0,autoListenJoined=lastPersisted.AutoListenJoined,membershipState=(source as OfficialBotSource)?.MembershipState,offset=MessageScroll.VerticalOffset,extent=MessageScroll.ExtentHeight,viewport=MessageScroll.ViewportHeight,geometry=WindowPlacement.Snapshot(this),nativeLayered=WindowAlpha.HasNativeLayered(this),dragHook=dragYield?.IsHooked,dragYielding=dragYield?.Yielding,browserWatch=dragYield?.BrowserWatchActive,yieldTimers=dragYield?.ActiveTimerCount,nativeTopmost=dragYield?.NativeTopmost,pinIntent=Pin.IsChecked==true,savedOpacity=lastPersisted.Opacity,font=MessageList.FontFamily.Source,fontSize=MessageList.FontSize,preferredFontSize=FontScale.Value,fitStatus=fitStatus,fitRequiredHeight=fitRequiredHeight,fitAvailableHeight=fitAvailableHeight,fitPasses=fitPasses,minimumFitFontSize=MinimumFitFontSize,autoPaging=false,autoReading=AutoScroll.IsChecked==true,dwellSeconds=reader.Seconds,readingTimerActive=readingTimer.IsEnabled,preferenceWrites=Preferences.WriteCount,newestMessageAt=readingQueue.LastOrDefault()?.SentAt,visibleOldestMessageAt=displayed.FirstOrDefault()?.SentAt,visibleNewestMessageAt=displayed.LastOrDefault()?.SentAt,pinnedMessageAt=pinnedLatest?.SentAt,checkedAt=DateTimeOffset.UtcNow});
    private void CreateTray(bool verify=false)
    {
        if(App.SmokeMode && !verify)return;
        tray=new System.Windows.Forms.NotifyIcon { Icon=System.Drawing.SystemIcons.Information,Text="飞书消息小窗",Visible=true };
        var menu=new System.Windows.Forms.ContextMenuStrip();
        menu.Items.Add("显示 / 隐藏",null,(_,_)=>Dispatcher.Invoke(()=>{if(IsVisible)Hide();else Restore();}));
        menu.Items.Add("置顶开关",null,(_,_)=>Dispatcher.Invoke(()=>{Pin.IsChecked=Pin.IsChecked!=true;PreferenceChanged(this,new());}));
        menu.Items.Add("设置",null,(_,_)=>Dispatcher.Invoke(()=>SettingsClick(this,new())));
        menu.Items.Add("恢复不透明并显示",null,(_,_)=>Dispatcher.Invoke(()=>{OpacityScale.Value=100;Restore();}));
        menu.Items.Add("退出",null,async (_,_)=>{ProcessLifecycle.ExitReason="tray_exit";await Dispatcher.InvokeAsync(ExitAsync).Task.Unwrap();});
        AddUpdateMenu(menu);tray.ContextMenuStrip=menu;tray.MouseDown+=(_,_)=>Dispatcher.Invoke(()=>dragYield?.OwnInput());
        menu.Opening+=(_,_)=>Dispatcher.Invoke(()=>dragYield?.OwnInput(true));menu.Closed+=(_,_)=>Dispatcher.Invoke(()=>dragYield?.MenuClosed());
        tray.DoubleClick+=(_,_)=>Dispatcher.Invoke(Restore);
    }
    internal void Restore(){Show();WindowState=WindowState.Normal;var work=SystemParameters.WorkArea;Left=Math.Clamp(Left,work.Left,Math.Max(work.Left,work.Right-Width));Top=Math.Clamp(Top,work.Top,Math.Max(work.Top,work.Bottom-Height));Activate();}
    private void HideClick(object sender,RoutedEventArgs e)=>Hide();
    private void TitleDrag(object sender,System.Windows.Input.MouseButtonEventArgs e)
    { if(e.OriginalSource is TextBlock && e.LeftButton==System.Windows.Input.MouseButtonState.Pressed)DragMove(); }
    private void UpdatePinnedChoices()
    {
        updatingPinnedChoice=true;
        var names=(source as OfficialBotSource)?.JoinedGroupNames ?? (source as CloudMessageSource)?.Groups;
        var choices=new List<KeyValuePair<string,string>>{new("","不置顶群消息")};
        choices.AddRange(selectedChats.Order(StringComparer.Ordinal).Select(id=>new KeyValuePair<string,string>(id,names is not null && names.TryGetValue(id,out var name)?name:id)));
        PinnedGroup.ItemsSource=choices;PinnedGroup.SelectedValue=selectedChats.Contains(pinnedChatId)?pinnedChatId:"";updatingPinnedChoice=false;
    }
    private async void PinnedGroupChanged(object sender,SelectionChangedEventArgs e)
    {
        if(!ready || updatingPinnedChoice || PinnedGroup.SelectedValue is not string id)return;
        if(source is CloudMessageSource cloud)
        {
            try{await cloud.SelectPinAsync(id);}
            catch{UpdatePinnedChoices();SetStatus("Cloud pinned selection was not saved; retry when connected");return;}
        }
        pinnedChatId=id;pinnedLatest=null;if(id.Length>0)store.KeepLatest(id);renderedRevision=-1;Render();SavePreferences();
    }
    private void SettingsClick(object sender,RoutedEventArgs e)
    {
        UpdatePinnedChoices();if(settingsWindow is not null){settingsWindow.Show();settingsWindow.Activate();return;}
        SettingsReading.SetBinding(ToggleButton.IsCheckedProperty,new System.Windows.Data.Binding("IsChecked"){Source=AutoScroll,Mode=System.Windows.Data.BindingMode.TwoWay});SettingsSound.SetBinding(ToggleButton.IsCheckedProperty,new System.Windows.Data.Binding("IsChecked"){Source=Sound,Mode=System.Windows.Data.BindingMode.TwoWay});SettingsPanel.Resources=Resources;Root.Children.Remove(SettingsPanel);SettingsPanel.Visibility=Visibility.Visible;
        settingsWindow=new Window{Title="飞书消息 · 设置",Width=420,Height=690,MinWidth=380,MinHeight=440,ShowInTaskbar=false,Topmost=true,Background=new SolidColorBrush(Color.FromRgb(255,255,255)),Foreground=Brushes.Black,Content=new ScrollViewer{Content=SettingsPanel,VerticalScrollBarVisibility=ScrollBarVisibility.Auto}};
        settingsWindow.Closing+=(_,args)=>{if(!exiting){args.Cancel=true;settingsWindow.Hide();}};
        settingsWindow.Show();
    }
    private void OpacityChanged(object sender,RoutedPropertyChangedEventArgs<double> e)
    {if(!ready)return;if(!WindowAlpha.Set(this,Math.Clamp(OpacityScale.Value/100,.6,1)))SetStatus("透明度设置失败 · 请从托盘恢复不透明");OpacityLabel.Text=$"背景透明度 {OpacityScale.Value:0}%";SavePreferences();}
    private void StartupClick(object sender,RoutedEventArgs e)
    {
        var wanted=Autostart.IsChecked==true;
        if(!StartupRegistration.TrySet(wanted)){Autostart.IsChecked=!wanted;SetStatus("自启设置失败 · 已回滚；没有更改其他自启项");}
    }
    private void ImportAudioClick(object sender,RoutedEventArgs e)
    {
        var picker=new Microsoft.Win32.OpenFileDialog{Filter="提示音 (*.wav;*.mp3)|*.wav;*.mp3",Title="选择你有权使用的本地音频（不上传）"};
        if(picker.ShowDialog()!=true)return;
        if(!AlertAudio.IsSupported(picker.FileName)){SetStatus("音频无效 · 仅支持 2MB 以内 WAV / MP3");return;}
        audio.PathName=picker.FileName;AudioLabel.Text=Path.GetFileName(picker.FileName);SavePreferences();
    }
    private void ResetAudioClick(object sender,RoutedEventArgs e){audio.PathName="";AudioLabel.Text=audio.PathName.Length==0?"系统提示音":Path.GetFileName(audio.PathName);SavePreferences();}
    private async void LoadSavedClick(object sender,RoutedEventArgs e)
    {
        var saved=CredentialVault.LoadOnUserRequest();if(saved is null){SetStatus("本地加密配置不可用 · 不会重新创建应用");return;}
        var dialog=new ConnectionWindow(saved){Owner=this};
        if(dialog.ShowDialog()==true && dialog.Settings is {} settings)await ConnectSettingsAsync(settings);
        saved.Secret="";
    }
    internal async Task ExitAsync()
    {
        if(exiting)return;SavePreferences();await FlushPreferencesAsync();
        if(pendingPreferences is not null){SetStatus("设置保存失败，原文件已保留；请重试退出");Restore();return;}
        ProcessLifecycle.Write("exit_requested",ProcessLifecycle.ExitReason);
        exiting=true;desktopUpdates?.Dispose();await webPublisher.DisposeAsync();dragYield?.Dispose();shutdown.Cancel();await StopAsync("已退出");
        readingTimer.Stop();readingIdleTimer.Stop();expiryTimer.Stop();preferenceTimer.Stop();scrollIdle.Stop();settingsWindow?.Close();audio.Dispose();tray?.ContextMenuStrip?.Dispose();tray?.Dispose();tray=null;
        shutdown.Dispose();Close();Application.Current.Shutdown();
    }
    private void OnClosing(object? sender, CancelEventArgs e)
    {
        if(exiting)return;
        e.Cancel=true;Hide();SavePreferences();
    }
}
