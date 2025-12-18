Get-ChildItem -Path "." -Filter "*.ppm" | ForEach-Object {
    # Perform operations on each file, represented by $_
    # Write-Host "Processing file: $($_.FullName)"
    # Example: Get content of the file
    # Get-Content $_.FullName
	$newName = "$($_.BaseName).png"
	echo $newName
	ffmpeg -i $_ $newName
}