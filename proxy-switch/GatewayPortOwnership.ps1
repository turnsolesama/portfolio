param([Parameter(Mandatory=$true)][int]$CorePID)
$ErrorActionPreference='Stop'
# Query only TCP listener ownership. No target process memory or command lines.
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
public static class FlowSwitchPortOwnership {
    [DllImport("iphlpapi.dll", SetLastError=true)]
    static extern uint GetExtendedTcpTable(IntPtr table, ref int size, bool order, int family, int tableClass, uint reserved);
    public static int[] Read(int owner) {
        int size=0; uint result=GetExtendedTcpTable(IntPtr.Zero,ref size,false,2,5,0);
        if(result!=0 && result!=122) throw new Win32Exception((int)result);
        for(int attempt=0;attempt<3;attempt++) {
            IntPtr table=Marshal.AllocHGlobal(size);
            try {
                result=GetExtendedTcpTable(table,ref size,false,2,5,0);
                if(result==122)continue;
                if(result!=0)throw new Win32Exception((int)result);
                int count=Marshal.ReadInt32(table); var ports=new List<int>();
                if(count<0 || count>(size-4)/24)throw new InvalidOperationException("tcp-table-size");
                for(int i=0;i<count;i++) {
                    int offset=4+i*24;
                    if(Marshal.ReadInt32(table,offset)!=2 || Marshal.ReadInt32(table,offset+20)!=owner)continue;
                    if(Marshal.ReadByte(table,offset+4)!=127 || Marshal.ReadByte(table,offset+5)!=0 || Marshal.ReadByte(table,offset+6)!=0 || Marshal.ReadByte(table,offset+7)!=1)continue;
                    ports.Add((Marshal.ReadByte(table,offset+8)<<8)|Marshal.ReadByte(table,offset+9));
                }
                return ports.ToArray();
            } finally {Marshal.FreeHGlobal(table);}
        }
        throw new InvalidOperationException("tcp-table-changed");
    }
}
'@
$process=[Diagnostics.Process]::GetProcessById($CorePID)
try {
    $start=$process.StartTime.ToUniversalTime().Ticks.ToString()
    $ports=@([FlowSwitchPortOwnership]::Read($CorePID))
    $process.Refresh()
    if($process.HasExited -or $process.StartTime.ToUniversalTime().Ticks.ToString() -cne $start){throw 'core-identity-changed'}
    @{ticks=$start;ports=$ports}|ConvertTo-Json -Compress
} finally {$process.Dispose()}
