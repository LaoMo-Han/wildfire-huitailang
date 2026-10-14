using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Runtime.Versioning;
[assembly: TargetFramework(".NETFramework,Version=v4.7.2")]

public sealed class UpdateComponent {
    public string id { get; set; } public string url { get; set; }
    public long size { get; set; } public string sha256 { get; set; }
    public Dictionary<string,string> files { get; set; }
}
public sealed class UpdateManifest {
    public int schema_version { get; set; } public string version { get; set; }
    public long build { get; set; } public string base_client { get; set; }
    public string notes { get; set; } public string published_at { get; set; }
    public List<UpdateComponent> components { get; set; }
    public List<string> remove { get; set; }
}
public sealed class BackupFile {
    public string path { get; set; } public bool existed { get; set; }
}
public sealed class ApplyJournal {
    public string stage { get; set; } public string state { get; set; }
    public List<BackupFile> files { get; set; }
}
public static class UpdateCore {
    public const string Site = "https://laomo-han.github.io/wildfire-downloads/";
    public const string ManifestUrl = Site+"latest.json";
    public static JavaScriptSerializer Serializer() { return new JavaScriptSerializer { MaxJsonLength=1048576 }; }
    public static T Read<T>(string path) { return Serializer().Deserialize<T>(File.ReadAllText(path,Encoding.UTF8)); }
    public static string Hash(string path) { using(var h=SHA256.Create()) using(var f=File.OpenRead(path)) return BitConverter.ToString(h.ComputeHash(f)).Replace("-","").ToLowerInvariant(); }
    public static string TextHash(string text) { using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(Encoding.UTF8.GetBytes(text))).Replace("-","").ToLowerInvariant(); }
    public static void Atomic(string path,string text) {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path)));
        var temp=path+".new-"+Guid.NewGuid().ToString("N");
        File.WriteAllText(temp,text,new UTF8Encoding(false));
        Replace(temp,path);
    }
    public static void Replace(string source,string target) {
        if(File.Exists(target))File.Replace(source,target,null);else File.Move(source,target);
    }
    public static Mutex RootMutex(string root) { return new Mutex(false,"Local\\Wildfire-"+TextHash(Path.GetFullPath(root).TrimEnd('\\').ToUpperInvariant()).Substring(0,24)); }
    public static bool Allowed(string path) {
        if(String.IsNullOrEmpty(path)||path.Contains("\\")||path.Contains(":")||path.StartsWith("/")||path.Split('/').Any(p=>p=="."||p==".."||p==""||p.TrimEnd(' ','.')!=p)) return false;
        if(path=="game/wf.exe"||path=="res/entities.bag"||path=="bootstrap/EditorConf.py")return true;
        if(path.StartsWith("res/editor/client/")&&path.EndsWith(".py")&&path.Split('/').Length==4)return true;
        return new[]{"launch.exe","update.exe","开始游戏.exe","start_offline.cmd","launch.exe.config","update.exe.config","开始游戏.exe.config"}.Contains(path);
    }
    public static string Inside(string root,string relative) {
        var absolute=Path.GetFullPath(Path.Combine(root,relative.Replace('/',Path.DirectorySeparatorChar)));
        var prefix=Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
        if(!absolute.StartsWith(prefix,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("更新路径越界");
        var current=new FileInfo(absolute).Directory;
        while(current!=null&&current.FullName.StartsWith(prefix,StringComparison.OrdinalIgnoreCase)) {
            if(current.Exists&&(current.Attributes&FileAttributes.ReparsePoint)!=0)throw new InvalidDataException("更新目录不支持符号链接");current=current.Parent;
        }
        if(File.Exists(absolute)&&(File.GetAttributes(absolute)&FileAttributes.ReparsePoint)!=0)throw new InvalidDataException("更新文件不支持符号链接");
        return absolute;
    }
    public static UpdateManifest Installed(string root) {
        try{return Read<UpdateManifest>(Path.Combine(root,"version.json"));}catch{return new UpdateManifest{version="旧版",build=0};}
    }
    public static void Validate(UpdateManifest manifest) {
        if(manifest==null||manifest.schema_version!=1||manifest.base_client!="1.0.192"||manifest.build<1||String.IsNullOrWhiteSpace(manifest.version)||manifest.version.Length>60||manifest.components==null||manifest.components.Count!=3)throw new InvalidDataException("更新清单格式不支持");
        var paths=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var ids=new HashSet<string>();
        foreach(var c in manifest.components) {
            if(!new[]{"core","runtime","launcher"}.Contains(c.id)||!ids.Add(c.id)||c.files==null||c.files.Count==0||c.size<=0||c.size>=2147483648L||!ValidHash(c.sha256))throw new InvalidDataException("更新组件格式错误");
            Uri uri; if(!Uri.TryCreate(c.url,UriKind.Absolute,out uri)||uri.Scheme!="https"||uri.Host!="github.com"||!uri.AbsolutePath.StartsWith("/LaoMo-Han/wildfire-downloads/releases/download/",StringComparison.Ordinal))throw new InvalidDataException("更新地址不受支持");
            foreach(var f in c.files)if(!Allowed(f.Key)||!paths.Add(f.Key)||!ValidHash(f.Value))throw new InvalidDataException("更新文件清单不安全");
        }
        foreach(var path in manifest.remove??new List<string>())if(!Allowed(path)||paths.Contains(path))throw new InvalidDataException("删除清单不安全");
    }
    public static bool ValidHash(string hash) { return hash!=null&&hash.Length==64&&hash.All(c=>"0123456789abcdef".Contains(c)); }
    public static UpdateManifest Fetch(string url=ManifestUrl) {
        var uri=new Uri(url);if(uri.Scheme!="https"||uri.Host!="laomo-han.github.io")throw new InvalidDataException("版本地址不安全");
        var request=(HttpWebRequest)WebRequest.Create(url+"?check="+DateTime.UtcNow.Ticks);
        request.Timeout=6000;request.ReadWriteTimeout=6000;request.UserAgent="Wildfire-Offline-Updater/1";
        using(var response=request.GetResponse())using(var stream=response.GetResponseStream())using(var memory=new MemoryStream()) {
            var bytes=new byte[8192];int n;while((n=stream.Read(bytes,0,bytes.Length))>0){memory.Write(bytes,0,n);if(memory.Length>1048576)throw new InvalidDataException("版本清单过大");}
            var manifest=Serializer().Deserialize<UpdateManifest>(Encoding.UTF8.GetString(memory.ToArray()));Validate(manifest);return manifest;
        }
    }
    public static bool Needed(string root,UpdateComponent c) { return c.files.Any(f=>!File.Exists(Inside(root,f.Key))||Hash(Inside(root,f.Key))!=f.Value); }
    public static void Download(UpdateComponent c,string target,Action<int> progress) {
        var partial=target+".part";var request=(HttpWebRequest)WebRequest.Create(c.url);request.Timeout=30000;request.ReadWriteTimeout=30000;request.UserAgent="Wildfire-Offline-Updater/1";
        try{using(var response=request.GetResponse())using(var stream=response.GetResponseStream())using(var file=File.Create(partial)) {
            var buffer=new byte[65536];long total=0;int n,last=-1;
            while((n=stream.Read(buffer,0,buffer.Length))>0){total+=n;if(total>c.size)throw new InvalidDataException("下载大小不符");file.Write(buffer,0,n);int p=(int)(total*100/c.size);if(p!=last){last=p;progress(p);}}
            if(total!=c.size)throw new InvalidDataException("下载不完整");
        }
        if(Hash(partial)!=c.sha256)throw new InvalidDataException("下载校验失败，请重试");Replace(partial,target);
        }catch{if(File.Exists(partial))File.Delete(partial);throw;}
    }
    public static void Extract(string archive,UpdateComponent c,string stage) {
        var seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);long expanded=0;
        using(var zip=ZipFile.OpenRead(archive))foreach(var entry in zip.Entries){
            if(entry.FullName.EndsWith("/"))continue;
            if(!c.files.ContainsKey(entry.FullName)||!Allowed(entry.FullName)||!seen.Add(entry.FullName)||((entry.ExternalAttributes>>16)&0xf000)==0xa000)throw new InvalidDataException("补丁中包含未授权文件");
            expanded+=entry.Length;if(expanded>268435456L||entry.Length>134217728L)throw new InvalidDataException("补丁解压大小异常");
            var target=Inside(Path.Combine(stage,"payload"),entry.FullName);Directory.CreateDirectory(Path.GetDirectoryName(target));
            using(var input=entry.Open())using(var output=File.Create(target)){input.CopyTo(output);}
            if(Hash(target)!=c.files[entry.FullName])throw new InvalidDataException("补丁文件校验失败");
        }
        if(seen.Count!=c.files.Count)throw new InvalidDataException("补丁缺少文件");
    }
    public static string Prepare(string root,UpdateManifest manifest,Action<string,int> progress) {
        Validate(manifest);
        var needed=manifest.components.Where(c=>Needed(root,c)).ToList();
        long space=needed.Sum(c=>c.size)*6+134217728;
        if(new DriveInfo(Path.GetPathRoot(Path.GetFullPath(root))).AvailableFreeSpace<space)throw new IOException("磁盘空间不足");
        var stage=Path.Combine(root,".updates",manifest.build+"-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(stage);
        foreach(var c in needed){var archive=Path.Combine(stage,c.id+".zip");progress(c.id,0);Download(c,archive,p=>progress(c.id,p));Extract(archive,c,stage);}
        Atomic(Path.Combine(stage,"manifest.json"),Serializer().Serialize(manifest));return stage;
    }
    static void CopyReplace(string source,string target) {
        Directory.CreateDirectory(Path.GetDirectoryName(target));var temp=target+".update-"+Guid.NewGuid().ToString("N");File.Copy(source,temp);Replace(temp,target);
    }
    public static void Recover(string root) {
        var journalPath=Path.Combine(root,".updates","journal.json");if(!File.Exists(journalPath))return;
        var journal=Read<ApplyJournal>(journalPath);var updateRoot=Path.Combine(root,".updates");
        var stage=Path.GetFullPath(journal.stage);if(!stage.StartsWith(Path.GetFullPath(updateRoot)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("恢复目录无效");
        if(journal.state!="applying")return;
        foreach(var f in journal.files.AsEnumerable().Reverse()) {
            if(!Allowed(f.path)&&f.path!="version.json")throw new InvalidDataException("恢复文件无效");
            var target=Inside(root,f.path);var backup=Inside(Path.Combine(stage,"backup"),f.path);
            if(f.existed){if(!File.Exists(backup))throw new IOException("恢复备份缺失");CopyReplace(backup,target);}else if(File.Exists(target))File.Delete(target);
        }
        journal.state="rolled_back";Atomic(journalPath,Serializer().Serialize(journal));
    }
    public static void Apply(string root,string stage,bool injectFailure=false,long? testAvailableSpace=null) {
        root=Path.GetFullPath(root);stage=Path.GetFullPath(stage);
        if(!stage.StartsWith(Path.Combine(root,".updates")+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("安装目录无效");
        Recover(root);var manifest=Read<UpdateManifest>(Path.Combine(stage,"manifest.json"));Validate(manifest);
        var changes=manifest.components.SelectMany(c=>c.files).Where(f=>File.Exists(Inside(Path.Combine(stage,"payload"),f.Key))).ToDictionary(f=>f.Key,f=>f.Value);
        foreach(var f in changes)if(Hash(Inside(Path.Combine(stage,"payload"),f.Key))!=f.Value)throw new InvalidDataException("待安装文件损坏");
        var paths=changes.Keys.Concat(manifest.remove??new List<string>()).Concat(new[]{"version.json"}).Distinct().ToList();
        long backupBytes=0,largest=0;
        foreach(var path in paths){
            var target=Inside(root,path);
            if(File.Exists(target)){
                long bytes=new FileInfo(target).Length;backupBytes+=bytes;largest=Math.Max(largest,bytes);
                // Check every target before changing the first one. A locked or read-only
                // file must not leave earlier components partially installed.
                using(var probe=new FileStream(target,FileMode.Open,FileAccess.ReadWrite,FileShare.None)){}
            }
        }
        foreach(var path in changes.Keys)largest=Math.Max(largest,new FileInfo(Inside(Path.Combine(stage,"payload"),path)).Length);
        long free=testAvailableSpace??new DriveInfo(Path.GetPathRoot(root)).AvailableFreeSpace;
        if(free<backupBytes+2*largest+16777216)throw new IOException("磁盘空间不足，尚未开始安装");
        var journal=new ApplyJournal{stage=stage,state="applying",files=new List<BackupFile>()};
        foreach(var path in paths){var target=Inside(root,path);var existed=File.Exists(target);if(existed){var backup=Inside(Path.Combine(stage,"backup"),path);Directory.CreateDirectory(Path.GetDirectoryName(backup));File.Copy(target,backup,true);}journal.files.Add(new BackupFile{path=path,existed=existed});}
        var journalPath=Path.Combine(root,".updates","journal.json");Atomic(journalPath,Serializer().Serialize(journal));
        try{
            int count=0;foreach(var f in changes){CopyReplace(Inside(Path.Combine(stage,"payload"),f.Key),Inside(root,f.Key));if(injectFailure&&++count==1)throw new IOException("Injected test failure");}
            foreach(var path in manifest.remove??new List<string>()){var target=Inside(root,path);if(File.Exists(target))File.Delete(target);}
            foreach(var c in manifest.components)foreach(var f in c.files)if(!File.Exists(Inside(root,f.Key))||Hash(Inside(root,f.Key))!=f.Value)throw new InvalidDataException("安装结果校验失败");
            Atomic(Path.Combine(root,"version.json"),Serializer().Serialize(manifest));journal.state="complete";Atomic(journalPath,Serializer().Serialize(journal));
            CleanOldStages(root,stage);
        }catch{Recover(root);throw;}
    }
    static void CleanOldStages(string root,string keep) {
        foreach(var directory in Directory.GetDirectories(Path.Combine(root,".updates"))){
            var absolute=Path.GetFullPath(directory);if(absolute==keep||!absolute.StartsWith(Path.GetFullPath(Path.Combine(root,".updates"))+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))continue;
            if((File.GetAttributes(absolute)&FileAttributes.ReparsePoint)!=0)continue;
            // Only directories created by this updater are eligible.
            var name=Path.GetFileName(absolute);long build;if(name.Length<34||!Int64.TryParse(name.Split('-')[0],out build))continue;
            try{Directory.Delete(absolute,true);}catch(IOException){}catch(UnauthorizedAccessException){}
        }
    }
}
