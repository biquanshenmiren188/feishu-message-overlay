using System.ComponentModel;
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
    private readonly MessageStore store = new();
    private readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromSeconds(1) };
    private readonly CancellationTokenSource shutdown = new();
    private IMessageSource? source;
    private bool ready, busy;
    private int generation;
    private HashSet<string> selectedChats = new(StringComparer.Ordinal);
    private LinkState? previousLinkState;
    private DateTimeOffset nextDemo;
    private int soundRequests;
    private bool exiting;
    private Window? settingsWindow;
    private readonly AlertAudio audio=new();
    private System.Windows.Forms.NotifyIcon? tray;
    public MainWindow()
    {
        InitializeComponent();
        var prefs = Preferences.Load();
        Width = double.IsFinite(prefs.Width) ? Math.Clamp(prefs.Width, 300, 1200) : 360;
        Height = double.IsFinite(prefs.Height) ? Math.Clamp(prefs.Height, 240, 1200) : 460;
        Pin.IsChecked = prefs.Topmost; Topmost = prefs.Topmost; Sound.IsChecked = prefs.Sound;
        FontChoice.ItemsSource = Fonts.SystemFontFamilies.OrderBy(f => f.Source).ToArray();
        FontChoice.SelectedItem = Fonts.SystemFontFamilies.FirstOrDefault(f => f.Source == prefs.Font) ?? new FontFamily("Microsoft YaHei UI");
        FontScale.Value = double.IsFinite(prefs.FontSize) ? Math.Clamp(prefs.FontSize, 12, 32) : 16;
        MessageList.FontFamily = (FontFamily)FontChoice.SelectedItem; MessageList.FontSize = FontScale.Value;
        OpacityScale.Value=double.IsFinite(prefs.Opacity)?Math.Clamp(prefs.Opacity*100,60,100):96;
        Opacity=OpacityScale.Value/100; OpacityLabel.Text=$"透明度 {OpacityScale.Value:0}%";
        audio.PathName=prefs.AudioPath; AudioLabel.Text=audio.PathName.Length==0?"系统提示音":Path.GetFileName(audio.PathName);
        Autostart.IsChecked=!App.SmokeMode && StartupRegistration.IsEnabled();
        CreateTray();
        timer.Tick += async (_, _) => await ReadAsync();
        Loaded += (_, _) => PlaceTopRight();
        SizeChanged += (_, _) => { if (ready) SavePreferences(); };
        ready = true;
    }
    private async Task StopAsync(string status)
    {
        generation++; timer.Stop(); var old = source; source = null;
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
            var messages = await current.ReadAsync(shutdown.Token);
            if (version != generation || source != current || shutdown.IsCancellationRequested) return;
            var added = false;
            foreach (var message in messages)
            {
                try { if (selectedChats.Contains(message.SourceId)) added |= store.Add(message, message.SourceId, DateTimeOffset.UtcNow); }
                catch (ArgumentException) { /* malformed message: skip, never log content */ }
            }
            store.Prune(DateTimeOffset.UtcNow); Render();
            if (added && Sound.IsChecked == true) { soundRequests++; if (!App.SmokeMode) audio.Play(); }
        }
        catch (OperationCanceledException) { }
        catch (DedupCapacityException) { await StopAsync("保护暂停 · 最近消息过多，请重新连接；未重播历史消息"); }
        catch (Exception) { await StopAsync(current is OfficialBotSource failed ? failed.Mode : "读取失败 · 已停止并清空，未记录消息内容"); }
        finally { busy = false; }
    }
    private void Render() { MessageList.ItemsSource = store.Items; EmptyHint.Visibility = store.Items.Count == 0 ? Visibility.Visible : Visibility.Collapsed; }
    private async void PauseClick(object sender, RoutedEventArgs e) => await StopAsync("已暂停 · 连接已关闭，消息已清空；可重新连接或演示");
    private void ClearClick(object sender, RoutedEventArgs e) { generation++; store.Clear(DateTimeOffset.UtcNow); Render(); }
    private async void ConnectClick(object sender, RoutedEventArgs e)
    {
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
            selectedChats = new(settings.ChatIds, StringComparer.Ordinal); store.Start(DateTimeOffset.UtcNow);
            source = await OfficialBotSource.StartAsync(ConnectionSettings.FindNode(), bridge, settings.AppId, settings.Secret, settings.ChatIds, settings.BotIds, shutdown.Token);
            timer.Start(); await ReadAsync();
        }
        catch (Exception) { await StopAsync("连接错误 · 请检查 Node运行时、桥接文件、应用配置及权限后重试"); }
        finally { settings.Secret = ""; }
    }
    private void SetStatus(string status) { Status.Text = status; Title = "飞书消息小窗 · " + status; }
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
    private void PreferenceChanged(object sender, RoutedEventArgs e) { if (!ready) return; Topmost = Pin.IsChecked == true; SavePreferences(); }
    private void FontChanged(object sender, SelectionChangedEventArgs e) { if (!ready) return; if (FontChoice.SelectedItem is FontFamily family) MessageList.FontFamily = family; SavePreferences(); }
    private void SizeChangedHandler(object sender, RoutedPropertyChangedEventArgs<double> e) { if (!ready) return; MessageList.FontSize = FontScale.Value; SavePreferences(); }
    private void SoundClick(object sender, RoutedEventArgs e) => audio.Play();
    private void PositionClick(object sender, RoutedEventArgs e) => PlaceTopRight();
    private void PlaceTopRight()
    {
        // WPF work-area coordinates are device-independent; PerMonitorV2 handles transitions.
        var work = SystemParameters.WorkArea;
        Width = Math.Min(Width, work.Width); Height = Math.Min(Height, work.Height);
        Left = Math.Max(work.Left, work.Right - Width - 16); Top = work.Top + 16;
    }
    private void SavePreferences()
    {
        if (App.SmokeMode) return;
        var saved = new Preferences { Width = Width, Height = Height, Topmost = Topmost, Sound = Sound.IsChecked == true, Font = MessageList.FontFamily.Source, FontSize = MessageList.FontSize, Opacity=Opacity, AudioPath=audio.PathName }.Save();
        if (!saved) Status.Text = "外观设置保存失败 · 当前会话仍可使用";
    }
    internal async Task RunSmokeAsync(string output)
    {
        Directory.CreateDirectory(output);
        void Assert(bool condition) { if (!condition) throw new InvalidOperationException("UI smoke assertion failed"); }
        Pin.IsChecked = false; PreferenceChanged(this, new()); Assert(!Topmost);
        Pin.IsChecked = true; PreferenceChanged(this, new()); Assert(Topmost);
        Width = 500; Height = 620; Assert(Width == 500 && Height == 620);
        FontScale.Value = 20; Assert(MessageList.FontSize == 20);
        FontChoice.SelectedItem = Fonts.SystemFontFamilies.First(f => f.Source == "Segoe UI");
        Assert(MessageList.FontFamily.Source == "Segoe UI");
        OpacityScale.Value=60;Assert(Opacity==.6);OpacityScale.Value=100;Assert(Opacity==1);
        Assert(!ShowInTaskbar);Close();Assert(!IsVisible && source is null);Restore();Assert(IsVisible);
        Autostart.IsChecked=true;StartupClick(this,new());Assert(Autostart.IsChecked==false);
        Sound.IsChecked = false;
        await StopAsync("模拟演示 · 非真实飞书消息"); source = new DemoSource(); selectedChats.Add("demo"); nextDemo = DateTimeOffset.MinValue; store.Start(DateTimeOffset.UtcNow);
        await ReadAsync(); Assert(store.Items.Count == 1 && EmptyHint.Visibility == Visibility.Collapsed);
        Width=360;Height=460;FontScale.Value=14;
        FontChoice.SelectedItem=Fonts.SystemFontFamilies.First(f=>f.Source=="Microsoft YaHei UI");
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
    private void CreateTray(bool verify=false)
    {
        if(App.SmokeMode && !verify)return;
        tray=new System.Windows.Forms.NotifyIcon { Icon=System.Drawing.SystemIcons.Information,Text="飞书消息小窗",Visible=true };
        var menu=new System.Windows.Forms.ContextMenuStrip();
        menu.Items.Add("显示 / 隐藏",null,(_,_)=>Dispatcher.Invoke(()=>{if(IsVisible)Hide();else Restore();}));
        menu.Items.Add("置顶开关",null,(_,_)=>Dispatcher.Invoke(()=>{Pin.IsChecked=Pin.IsChecked!=true;PreferenceChanged(this,new());}));
        menu.Items.Add("设置",null,(_,_)=>Dispatcher.Invoke(()=>SettingsClick(this,new())));
        menu.Items.Add("恢复不透明并显示",null,(_,_)=>Dispatcher.Invoke(()=>{OpacityScale.Value=100;Restore();}));
        menu.Items.Add("退出",null,async (_,_)=>await Dispatcher.InvokeAsync(ExitAsync).Task.Unwrap());
        tray.ContextMenuStrip=menu;tray.DoubleClick+=(_,_)=>Dispatcher.Invoke(Restore);
    }
    internal void Restore(){Show();WindowState=WindowState.Normal;var work=SystemParameters.WorkArea;Left=Math.Clamp(Left,work.Left,Math.Max(work.Left,work.Right-Width));Top=Math.Clamp(Top,work.Top,Math.Max(work.Top,work.Bottom-Height));Activate();}
    private void HideClick(object sender,RoutedEventArgs e)=>Hide();
    private void TitleDrag(object sender,System.Windows.Input.MouseButtonEventArgs e)
    { if(e.OriginalSource is TextBlock && e.LeftButton==System.Windows.Input.MouseButtonState.Pressed)DragMove(); }
    private void SettingsClick(object sender,RoutedEventArgs e)
    {
        if(settingsWindow is not null){settingsWindow.Show();settingsWindow.Activate();return;}
        Root.Children.Remove(SettingsPanel);SettingsPanel.Visibility=Visibility.Visible;
        settingsWindow=new Window{Title="飞书消息 · 设置",Width=420,Height=690,MinWidth=380,MinHeight=440,ShowInTaskbar=false,Topmost=true,Background=System.Windows.Media.Brushes.White,Content=new ScrollViewer{Content=SettingsPanel,VerticalScrollBarVisibility=ScrollBarVisibility.Auto}};
        settingsWindow.Closing+=(_,args)=>{if(!exiting){args.Cancel=true;settingsWindow.Hide();}};
        settingsWindow.Show();
    }
    private void OpacityChanged(object sender,RoutedPropertyChangedEventArgs<double> e)
    {if(!ready)return;Opacity=Math.Clamp(OpacityScale.Value/100,.6,1);OpacityLabel.Text=$"透明度 {OpacityScale.Value:0}%";SavePreferences();}
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
    private void ResetAudioClick(object sender,RoutedEventArgs e){audio.PathName="";AudioLabel.Text="系统提示音";SavePreferences();}
    private async void LoadSavedClick(object sender,RoutedEventArgs e)
    {
        var saved=CredentialVault.LoadOnUserRequest();if(saved is null){SetStatus("本地加密配置不可用 · 不会重新创建应用");return;}
        var dialog=new ConnectionWindow(saved){Owner=this};
        if(dialog.ShowDialog()==true && dialog.Settings is {} settings)await ConnectSettingsAsync(settings);
        saved.Secret="";
    }
    internal async Task ExitAsync()
    {
        if(exiting)return;exiting=true;shutdown.Cancel();SavePreferences();await StopAsync("已退出");
        settingsWindow?.Close();audio.Dispose();tray?.ContextMenuStrip?.Dispose();tray?.Dispose();tray=null;
        shutdown.Dispose();Close();Application.Current.Shutdown();
    }
    private void OnClosing(object? sender, CancelEventArgs e)
    {
        if(exiting)return;
        e.Cancel=true;Hide();SavePreferences();
    }
}
