<#
Exports a restored Cabinet Vision report database to a JSON file, for "Import" on a Cabinet Vision Job.

Run in PowerShell on the machine with SQL Server (it only reads; nothing in the database changes):

    .\export_cabinet_vision.ps1 -Database report5
    .\export_cabinet_vision.ps1 -Database report5 -Server ".\SQLEXPRESS" -Out "C:\Users\Public\Norton.json"

Uses Windows sign-in to SQL Server (as SSMS does). If Windows blocks the script, run it with:

    powershell -ExecutionPolicy Bypass -File .\export_cabinet_vision.ps1 -Database report5
#>
param(
	[Parameter(Mandatory = $true)][string]$Database,
	[string]$Server = ".\SQLEXPRESS",
	[string]$Out = ""
)
$ErrorActionPreference = "Stop"
if (-not $Out) { $Out = Join-Path (Get-Location) "$Database-cabinet-vision.json" }

# Every table in the database as JSON, keyed by table name; binary columns (images) left out.
$sql = @'
SET NOCOUNT ON;
DECLARE @tables nvarchar(max) = N'', @name sysname, @cols nvarchar(max), @sql nvarchar(max), @part nvarchar(max);
DECLARE t CURSOR LOCAL FAST_FORWARD FOR
	SELECT name FROM sys.tables WHERE is_ms_shipped = 0 AND name <> N'ReportTempAssets' ORDER BY name;
OPEN t;
FETCH NEXT FROM t INTO @name;
WHILE @@FETCH_STATUS = 0
BEGIN
	SELECT @cols = STRING_AGG(CAST(QUOTENAME(c.name) AS nvarchar(max)), N',') WITHIN GROUP (ORDER BY c.column_id)
	FROM sys.columns c
	WHERE c.object_id = OBJECT_ID(QUOTENAME(@name)) AND c.system_type_id NOT IN (34, 165, 173, 189);
	IF @cols IS NOT NULL
	BEGIN
		SET @sql = N'SET @out = (SELECT ' + @cols + N' FROM ' + QUOTENAME(@name) + N' FOR JSON PATH, INCLUDE_NULL_VALUES)';
		SET @part = NULL;
		EXEC sp_executesql @sql, N'@out nvarchar(max) OUTPUT', @out = @part OUTPUT;
		SET @tables += CASE WHEN @tables = N'' THEN N'' ELSE N',' END
			+ N'"' + STRING_ESCAPE(@name, 'json') + N'":' + ISNULL(@part, N'[]');
	END
	FETCH NEXT FROM t INTO @name;
END
CLOSE t;
DEALLOCATE t;
SELECT N'{"format":"cabinet-vision-report","version":1,"database":"' + STRING_ESCAPE(DB_NAME(), 'json')
	+ N'","exported_on":"' + CONVERT(nvarchar(30), SYSDATETIME(), 126) + N'","tables":{' + @tables + N'}}';
'@

$connection = New-Object System.Data.SqlClient.SqlConnection(
	"Server=$Server;Database=$Database;Integrated Security=True;TrustServerCertificate=True;Application Name=Cabinet Vision Export")
try {
	$connection.Open()
	$command = $connection.CreateCommand()
	$command.CommandText = $sql
	$command.CommandTimeout = 600
	$json = [string]$command.ExecuteScalar()
}
finally {
	$connection.Dispose()
}
if (-not $json) { throw "Nothing exported from $Database - is it a Cabinet Vision report database?" }
[IO.File]::WriteAllText($Out, $json, (New-Object System.Text.UTF8Encoding $false))
Write-Host "Exported $Database to $Out ($([math]::Round($json.Length / 1KB)) KB) - attach it to a Cabinet Vision Job and click Import."
