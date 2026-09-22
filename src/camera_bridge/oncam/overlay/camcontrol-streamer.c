#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#define BUFFER_SIZE 16384
#define VIEW_PATH "/tmp/view"

static volatile sig_atomic_t running = 1;

static int daemonize(void) {
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid > 0) return 1;
    if (setsid() < 0) return -1;
    pid = fork();
    if (pid < 0) return -1;
    if (pid > 0) _exit(0);
    return 0;
}

static void stop_streamer(int signal_number) {
    (void)signal_number;
    running = 0;
}

static int config_value(const char *name, char *value, size_t value_size) {
    FILE *file = fopen("/home/yi-hack-v3/camcontrol/camcontrol.conf", "r");
    char line[1024];
    size_t name_length = strlen(name);
    if (!file) return -1;
    while (fgets(line, sizeof(line), file)) {
        if (strncmp(line, name, name_length) == 0 && line[name_length] == '=') {
            snprintf(value, value_size, "%s", line + name_length + 1);
            value[strcspn(value, "\r\n")] = '\0';
            fclose(file);
            return 0;
        }
    }
    fclose(file);
    return -1;
}

static int parse_endpoint(const char *endpoint, char *host, size_t host_size, char *port, size_t port_size) {
    const char *start = strstr(endpoint, "http://");
    const char *colon;
    if (!start) return -1;
    start += 7;
    colon = strrchr(start, ':');
    if (!colon || strchr(colon, '/')) return -1;
    snprintf(host, host_size, "%.*s", (int)(colon - start), start);
    snprintf(port, port_size, "%s", colon + 1);
    return 0;
}

static int connect_relay(const char *host, const char *port) {
    struct addrinfo hints, *result, *entry;
    int socket_fd = -1;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(host, port, &hints, &result) != 0) return -1;
    for (entry = result; entry; entry = entry->ai_next) {
        socket_fd = socket(entry->ai_family, entry->ai_socktype, entry->ai_protocol);
        if (socket_fd >= 0 && connect(socket_fd, entry->ai_addr, entry->ai_addrlen) == 0) break;
        if (socket_fd >= 0) close(socket_fd);
        socket_fd = -1;
    }
    freeaddrinfo(result);
    return socket_fd;
}

static int write_all(int socket_fd, const void *buffer, size_t length) {
    const char *cursor = buffer;
    while (length > 0) {
        ssize_t written = send(socket_fd, cursor, length, 0);
        if (written <= 0) return -1;
        cursor += written;
        length -= (size_t)written;
    }
    return 0;
}

static int send_frame(const char *host, const char *port, const char *camera_id, const char *camera_key) {
    struct stat view_stat;
    char header[2048];
    char buffer[BUFFER_SIZE];
    int view_fd, socket_fd;
    ssize_t read_size;
    if (stat(VIEW_PATH, &view_stat) != 0 || view_stat.st_size <= 0) return -1;
    view_fd = open(VIEW_PATH, O_RDONLY);
    if (view_fd < 0) return -1;
    socket_fd = connect_relay(host, port);
    if (socket_fd < 0) { close(view_fd); return -1; }
    snprintf(header, sizeof(header),
        "POST /api/cameras/%s/push-snapshot HTTP/1.1\r\n"
        "Host: %s\r\nContent-Type: video/h264\r\n"
        "Content-Length: %ld\r\nX-Camera-Key: %s\r\n"
        "Connection: close\r\n\r\n",
        camera_id, host, (long)view_stat.st_size, camera_key);
    if (write_all(socket_fd, header, strlen(header)) != 0) goto failed;
    while ((read_size = read(view_fd, buffer, sizeof(buffer))) > 0) {
        if (write_all(socket_fd, buffer, (size_t)read_size) != 0) goto failed;
    }
    close(socket_fd);
    close(view_fd);
    return read_size < 0 ? -1 : 0;
failed:
    close(socket_fd);
    close(view_fd);
    return -1;
}

int main(void) {
    char endpoint[256], host[128], port[16], camera_id[128], camera_key[128], interval_text[16];
    unsigned int interval = 1;
    if (daemonize() != 0) return 0;
    signal(SIGTERM, stop_streamer);
    signal(SIGINT, stop_streamer);
    while (running) {
        if (config_value("api_endpoint", endpoint, sizeof(endpoint)) == 0 &&
            config_value("camera_id", camera_id, sizeof(camera_id)) == 0 &&
            config_value("api_key", camera_key, sizeof(camera_key)) == 0 &&
            parse_endpoint(endpoint, host, sizeof(host), port, sizeof(port)) == 0) {
            if (config_value("push_interval_seconds", interval_text, sizeof(interval_text)) == 0) {
                interval = (unsigned int)strtoul(interval_text, NULL, 10);
            }
            /* The overlay owns a local wired/LAN hop; cap legacy uploader
             * settings at one second so it provides the low-latency path. */
            if (interval == 0 || interval > 1) interval = 1;
            send_frame(host, port, camera_id, camera_key);
        }
        sleep(interval);
    }
    return 0;
}