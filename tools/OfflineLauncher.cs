using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

// The original launcher forwards its window handle as the first hex argument.
// This local launcher provides that endpoint without displaying a launcher UI.
sealed class OfflineLauncher : NativeWindow
{
    private readonly Process client;
    private readonly Timer timer;

    private OfflineLauncher(string root)
    {
        CreateParams parameters = new CreateParams();
        parameters.Caption = "Wildfire Offline Launcher";
        parameters.Parent = new IntPtr(-3); // HWND_MESSAGE: no visible window.
        CreateHandle(parameters);
        string executable = Path.Combine(root, "game", "wf.exe");
        ProcessStartInfo start = new ProcessStartInfo(executable);
        start.WorkingDirectory = Path.GetDirectoryName(executable);
        start.Arguments = Handle.ToInt64().ToString("x");
        start.UseShellExecute = false;
        client = Process.Start(start);
        timer = new Timer();
        timer.Interval = 1000;
        timer.Tick += delegate
        {
            if (client.HasExited)
            {
                timer.Stop();
                DestroyHandle();
                client.Dispose();
                Application.ExitThread();
            }
        };
        timer.Start();
    }

    [STAThread]
    static int Main()
    {
        string root = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, ".."));
        try
        {
            OfflineLauncher launcher = new OfflineLauncher(root);
            Application.Run();
            GC.KeepAlive(launcher);
            return 0;
        }
        catch (Exception error)
        {
            File.WriteAllText(Path.Combine(root, "game", "offline_launcher_error.log"), error.ToString());
            return 1;
        }
    }
}
