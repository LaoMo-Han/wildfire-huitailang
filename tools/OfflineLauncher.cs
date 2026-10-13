using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

// The original launcher forwards its window handle as the first hex argument.
// This local launcher provides that endpoint without displaying a launcher UI.
sealed class OfflineLauncher : NativeWindow
{
    private delegate IntPtr WindowProc(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);
    private static readonly WindowProc DefaultProc = DefWindowProc;
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WindowClass
    {
        public uint style;
        public IntPtr procedure;
        public int classExtra, windowExtra;
        public IntPtr instance, icon, cursor, background;
        public string menuName, className;
    }
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern ushort RegisterClass(ref WindowClass value);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr DefWindowProc(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateWindowEx(uint extendedStyle, string className,
        string title, uint style, int x, int y, int width, int height,
        IntPtr parent, IntPtr menu, IntPtr instance, IntPtr parameter);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr GetModuleHandle(string name);
    private readonly Process client;
    private readonly Timer timer;

    private OfflineLauncher(string root)
    {
        WindowClass windowClass = new WindowClass();
        windowClass.className = "TW2LAUNCH";
        windowClass.instance = GetModuleHandle(null);
        windowClass.procedure = Marshal.GetFunctionPointerForDelegate(DefaultProc);
        if (RegisterClass(ref windowClass) == 0)
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        // Create directly so WinForms does not replace the compatibility class
        // name with its own generated window class name.
        IntPtr window = CreateWindowEx(0x80, "TW2LAUNCH", "tw2launch", 0x80000000,
            0, 0, 1, 1, IntPtr.Zero, IntPtr.Zero, windowClass.instance, IntPtr.Zero);
        if (window == IntPtr.Zero)
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        AssignHandle(window);
        string executable = Path.Combine(root, "game", "wf.exe");
        ProcessStartInfo start = new ProcessStartInfo(executable);
        start.WorkingDirectory = Path.GetDirectoryName(executable);
        // Match the original launcher's "%x %s" layout, including the separator
        // when there are no additional arguments.
        start.Arguments = Handle.ToInt64().ToString("x") + " ";
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
