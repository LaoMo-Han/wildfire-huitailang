using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

static class StartGame
{
    [STAThread]
    static void Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.Combine(root, "start_offline.cmd");
        try
        {
            if (!File.Exists(script))
                throw new FileNotFoundException("请把开始游戏.exe放在start_offline.cmd旁边。", script);
            ProcessStartInfo start = new ProcessStartInfo(
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "cmd.exe"));
            start.Arguments = "/d /s /c \"\"" + script + "\"\"";
            start.WorkingDirectory = root;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.WindowStyle = ProcessWindowStyle.Hidden;
            using (Process process = Process.Start(start))
            {
                process.WaitForExit();
                if (process.ExitCode != 0)
                    throw new InvalidOperationException("启动脚本执行失败，请确认客户端文件完整。错误码：" + process.ExitCode);
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "无法启动游戏", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
