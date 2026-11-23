on run
	set uid to do shell script "id -u"
	try
		do shell script "curl -s -m 2 http://127.0.0.1:8765/api/status >/dev/null"
	on error
		do shell script "launchctl kickstart gui/" & uid & "/com.local.llm-hub || true"
		delay 3
	end try
	open location "http://127.0.0.1:8765"
end run
