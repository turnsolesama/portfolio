param([Parameter(Mandatory=$true)][string]$RequestBase64)
$ErrorActionPreference='Stop'
# Only used to recover an existing lock. The normal acquisition path stays in Node.
$request=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($RequestBase64))|ConvertFrom-Json
$stream=$null
try {
    try {$stream=New-Object IO.FileStream($request.path,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::Read)}
    catch [IO.FileNotFoundException] {Write-Output 'changed';return}
    catch [IO.DirectoryNotFoundException] {Write-Output 'changed';return}
    catch [IO.IOException] {Write-Output 'busy';return}
    if($stream.Length -gt 4096){Write-Output 'busy';return}
    $bytes=New-Object byte[] ([int]$stream.Length)
    $offset=0
    while($offset -lt $bytes.Length){$count=$stream.Read($bytes,$offset,$bytes.Length-$offset);if($count -eq 0){throw 'Incomplete lock read'};$offset+=$count}
    $text=[Text.Encoding]::UTF8.GetString($bytes).TrimStart([char]0xFEFF)
    if($text -cne $request.expected){Write-Output 'changed';return}
    $prior=$null
    try {$prior=$text|ConvertFrom-Json}catch{}
    # Recheck process identity while holding the file exclusively; never evict
    # a live legacy owner or a writer still holding its initially empty file.
    if($prior -and $prior.pid -is [ValueType] -and $prior.pid -gt 0 -and $prior.pid -le [int]::MaxValue -and [math]::Truncate($prior.pid) -eq $prior.pid){
        $ownerProcess=$null
        try {$ownerProcess=[Diagnostics.Process]::GetProcessById([int]$prior.pid)}
        catch [ArgumentException] {} # No process with that PID.
        if($ownerProcess){
            try {
                if(-not $prior.startTicks -or $ownerProcess.StartTime.ToUniversalTime().Ticks.ToString() -ceq [string]$prior.startTicks){Write-Output 'busy';return}
            }finally{$ownerProcess.Dispose()}
        }
    }
    $replacement=[Text.Encoding]::UTF8.GetBytes([string]$request.owner)
    $stream.Position=0;$stream.Write($replacement,0,$replacement.Length);$stream.SetLength($replacement.Length);$stream.Flush($true)
    Write-Output 'acquired'
}finally{if($stream){$stream.Dispose()}}
