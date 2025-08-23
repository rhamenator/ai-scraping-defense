param()
if (Get-Command Install-WindowsFeature -ErrorAction SilentlyContinue) {
  $features = @("Web-Server","Web-WebServer","Web-Common-Http","Web-Default-Doc","Web-Static-Content","Web-Http-Errors","Web-Http-Redirect","Web-ISAPI-Ext","Web-ISAPI-Filter","Web-Mgmt-Tools","Web-Mgmt-Service")
  foreach ($f in $features) { try { Install-WindowsFeature -Name $f -IncludeManagementTools -ErrorAction SilentlyContinue | Out-Null } catch {} }
}
Import-Module WebAdministration -ErrorAction SilentlyContinue
