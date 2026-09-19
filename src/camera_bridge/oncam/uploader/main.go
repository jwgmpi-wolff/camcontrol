package main

import (
	"bytes"
	"crypto/tls"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"time"
)

func main() {
	endpoint := flag.String("endpoint", "", "Azure snapshot ingestion URL")
	key := flag.String("key", "", "per-camera credential")
	file := flag.String("file", "/tmp/view", "H.264 preview buffer")
	listen := flag.String("listen", "", "TCP address to relay")
	target := flag.String("target", "", "TCP relay target address")
	flag.Parse()
	if *listen != "" || *target != "" {
		if *listen == "" || *target == "" {
			fmt.Fprintln(os.Stderr, "listen and target are required together")
			os.Exit(2)
		}
		if err := relay(*listen, *target); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}
	if *endpoint == "" || *key == "" {
		fmt.Fprintln(os.Stderr, "endpoint and key are required")
		os.Exit(2)
	}
	payload, err := os.ReadFile(*file)
	if err != nil || len(payload) == 0 {
		fmt.Fprintln(os.Stderr, "could not read preview buffer")
		os.Exit(1)
	}
	client := &http.Client{
		Timeout: 20 * time.Second,
		Transport: &http.Transport{TLSClientConfig: &tls.Config{MinVersion: tls.VersionTLS12}},
	}
	req, err := http.NewRequest(http.MethodPost, *endpoint, bytes.NewReader(payload))
	if err != nil {
		os.Exit(1)
	}
	req.Header.Set("Content-Type", "video/h264")
	req.Header.Set("X-Camera-Key", *key)
	response, err := client.Do(req)
	if err != nil {
		os.Exit(1)
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, response.Body)
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		os.Exit(1)
	}
}

func relay(listen, target string) error {
	listener, err := net.Listen("tcp", listen)
	if err != nil {
		return err
	}
	defer listener.Close()
	for {
		client, err := listener.Accept()
		if err != nil {
			return err
		}
		go relayConnection(client, target)
	}
}

func relayConnection(client net.Conn, target string) {
	defer client.Close()
	upstream, err := net.DialTimeout("tcp", target, 10*time.Second)
	if err != nil {
		return
	}
	defer upstream.Close()
	go io.Copy(upstream, client)
	io.Copy(client, upstream)
}