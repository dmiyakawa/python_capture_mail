# これは何

/etc/aliases 等に仕掛けてメールをパースするプログラム

```
capture:  "|/path/to/capture.py"
```

とすると (その上で ``newaliases`` を実行すると) 同メールアドレスに送られた
メールを単にsyslogにダンプする。

# License

MIT
