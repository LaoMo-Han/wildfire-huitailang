using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

// Client 1.0.192 parses "-redirect <decimal HWND>" and checks IsWindow.
// The local message endpoint has no visible UI and stays alive with the child.
sealed class OfflineLauncher : NativeWindow
{
    private Process client;
    private Timer timer;
    private OfflineLauncher(string root)
    {
        CreateParams parameters = new CreateParams();
        parameters.Caption = "tw2launch";
        parameters.Width = parameters.Height = 1;
        parameters.Style = unchecked((int)0x80000000);
        CreateHandle(parameters);
        string executable = Path.Combine(root, "game", "wf.exe");
        ProcessStartInfo start = new ProcessStartInfo(executable);
        start.WorkingDirectory = Path.GetDirectoryName(executable);
        start.Arguments = "-redirect " + Handle.ToInt64().ToString();
        start.UseShellExecute = false;
        client = Process.Start(start);
        timer = new Timer();
        timer.Interval = 500;
        timer.Tick += delegate {
            if (client.HasExited) {
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
        string root = Path.GetFullPath(AppDomain.CurrentDomain.BaseDirectory);
        string errorLog = Path.Combine(root, "game", "offline_launcher_error.log");
        try {
            if (File.Exists(errorLog)) File.Delete(errorLog);
            File.Copy(Path.Combine(root, "bootstrap", "EditorConf.py"),
                      Path.Combine(root, "res", "editor", "client", "EditorConf.py"), true);
            OfflineLauncher launcher = new OfflineLauncher(root);
            Application.Run();
            GC.KeepAlive(launcher);
            return 0;
        } catch (Exception error) {
            File.WriteAllText(errorLog, error.ToString());
            return 1;
        }
    }
}
