param([Parameter(Mandatory=$true)][string]$Path)
$ErrorActionPreference='Stop'
$key=(Resolve-Path -LiteralPath $Path).Path
$temp=$key+'.owner-fix.tmp'
if(Test-Path -LiteralPath $temp){throw 'A replacement file already exists; inspect it first'}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$security=[Security.AccessControl.FileSecurity]::new()
$security.SetAccessRuleProtection($true,$false)
$security.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($identity.User,[Security.AccessControl.FileSystemRights]::FullControl,[Security.AccessControl.AccessControlType]::Allow))
# Create with a restricted ACL atomically, including when the original is
# owned by an old sandbox account and its ACL cannot be changed directly.
$source=[IO.File]::OpenRead($key)
try {
 $dest=[IO.FileSystemAclExtensions]::Create([IO.FileInfo]::new($temp),[IO.FileMode]::CreateNew,[Security.AccessControl.FileSystemRights]::FullControl,[IO.FileShare]::None,4096,[IO.FileOptions]::None,$security)
 try{$source.CopyTo($dest);$dest.Flush($true)}finally{$dest.Dispose()}
}finally{$source.Dispose()}
if((Get-FileHash -LiteralPath $key).Hash -ne (Get-FileHash -LiteralPath $temp).Hash){throw 'Copy verification failed'}
Move-Item -LiteralPath $temp -Destination $key -Force
$acl=Get-Acl -LiteralPath $key
if(-not $acl.AreAccessRulesProtected -or $acl.Access.Count -ne 1){throw 'ACL verification failed'}
Write-Output 'Private key preserved; owner and access restricted to the current account.'
