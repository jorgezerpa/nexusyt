import yt_dlp
import psutil

PROXY_COST_PER_GB = 7.5 # 7.5$

def measure_exact_traffic(url: str) -> dict:
    ydl_opts_meta = {
        'format': 'm4a/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
    }

    # 1. Snapshot network counters BEFORE the request
    net_before = psutil.net_io_counters()

    # 2. Run the yt_dlp extraction
    with yt_dlp.YoutubeDL(ydl_opts_meta) as ydl:
        info = ydl.extract_info(url, download=False)
        payload_bytes = info.get('filesize_approx') or info.get('filesize') or 0
        duration_secs = info.get("duration") or 0

    # 3. Snapshot network counters AFTER the request
    net_after = psutil.net_io_counters()

    # 4. Calculate the exact difference of the metadata extraction
    bytes_sent = net_after.bytes_sent - net_before.bytes_sent
    bytes_recv = net_after.bytes_recv - net_before.bytes_recv
    extraction_traffic = bytes_sent + bytes_recv

    # 5. Add the file size and network overhead
    total_traffic_bytes = extraction_traffic + (payload_bytes * 1.04)

    total_gb = total_traffic_bytes / (1024**3)
    exact_cost = total_gb * PROXY_COST_PER_GB

    duration_mins = duration_secs / 60
    cost_per_minute = exact_cost / duration_mins if duration_mins > 0 else 0

    return {
        "video_duration_minutes": duration_mins,
        "total_traffic_bytes": total_traffic_bytes,
        "total_cost": exact_cost,
        "total_cost_real_life": exact_cost * 1.20,
        "cost_per_minute": cost_per_minute,
        "cost_per_minute_real_life": cost_per_minute * 1.20
    }




if __name__ == "__main__":
    # to ensure the system-wide network counters are accurate.
    proxy_consumption = measure_exact_traffic(url="https://www.youtube.com/watch?v=x2i5Jp7mdMc&")
    minute_cost = proxy_consumption.get('cost_per_minute_real_life')


    print("Domestic Proxy Pool Costs Analisis")
    print("Most basic (and expensive) plans charges 7.5$ per GB of traffic.")
    print("- Stimated costs per video duration:")

    print(f"  - Total traffic {proxy_consumption.get('total_traffic_bytes')}")
    print(f"  - 1 minute: ${minute_cost:.6f}")
    print(f"  - 5 minutes: ${minute_cost*5:.6f}")
    print(f"  - 30 minutes: ${minute_cost*30:.6f}")
    print(f"  - 1 hour: ${minute_cost*60:.6f}")


































## most precise version
# import yt_dlp
# import logging
# import psutil
# import os

# logging.basicConfig(level=logging.INFO, format='%(message)s')
# logger = logging.getLogger("PipelineLogger")
# COST_PER_GB = 7.50

# def measure_exact_traffic(url: str):
#     logger.info(f"Analyzing video: {url}")
    
#     ydl_opts_meta = {
#         'format': 'm4a/bestaudio/best',
#         'quiet': True,
#         'no_warnings': True,
#         # If you are using a proxy, add it here:
#         # 'proxy': 'http://username:password@proxy.provider.com:port'
#     }

#     # 1. Snapshot network counters BEFORE the request
#     net_before = psutil.net_io_counters()

#     # 2. Run the yt_dlp extraction
#     with yt_dlp.YoutubeDL(ydl_opts_meta) as ydl:
#         info = ydl.extract_info(url, download=False)
#         payload_bytes = info.get('filesize_approx') or info.get('filesize') or 0

#     # 3. Snapshot network counters AFTER the request
#     net_after = psutil.net_io_counters()

#     # 4. Calculate the exact difference
# # 4. Calculate the exact difference of the metadata extraction
#     bytes_sent = net_after.bytes_sent - net_before.bytes_sent
#     bytes_recv = net_after.bytes_recv - net_before.bytes_recv
#     extraction_traffic = bytes_sent + bytes_recv

#     # 5. Add the file size and network overhead
#     total_traffic_bytes = extraction_traffic + (payload_bytes * 1.04)

#     total_gb = total_traffic_bytes / (1024**3)
#     exact_cost = total_gb * COST_PER_GB

#     duration_mins = info.get("duration") / 60

#     logger.info(f"--- Exact Network Measurement ---")
#     logger.info(f"Audio Payload Size: {payload_bytes / (1024**2):.2f} MB")
#     logger.info(f"Actual Upload:      {bytes_sent / (1024**2):.2f} MB")
#     logger.info(f"Actual Download:    {bytes_recv / (1024**2):.2f} MB")
#     logger.info(f"Total Proxy Traffic:{total_traffic_bytes / (1024**2):.2f} MB")
#     logger.info(f"Exact Proxy Cost:   ${exact_cost:.6f}")
#     if duration_mins > 0:
#         logger.info(f"total duration:     {duration_mins:.1f}min")
#         logger.info(f"Cost per minute:    ${exact_cost / duration_mins:.6f}")
#         logger.info(f"Real life cost (+20% ):    ${(exact_cost / duration_mins)*1.20:.6f}")

#     logger.info(f"---------------------------------\n")

# if __name__ == "__main__":
#     # NOTE: Close background apps (Spotify, heavy browser tabs) 
#     # to ensure the system-wide network counters are accurate.
#     measure_exact_traffic(url="https://www.youtube.com/watch?v=zIwLWfaAg-8")




















## MEASURES REAL TRAPHIC ONLY AKA HAS TO DOWNLOAD THE FILE
# import yt_dlp
# import logging
# import psutil
# import os

# logging.basicConfig(level=logging.INFO, format='%(message)s')
# logger = logging.getLogger("PipelineLogger")
# COST_PER_GB = 7.50

# def measure_exact_traffic(url: str):
#     logger.info(f"Analyzing video: {url}")
    
#     ydl_opts_meta = {
#         'format': 'm4a/bestaudio/best',
#         'quiet': True,
#         'no_warnings': True,
#         # If you are using a proxy, add it here:
#         # 'proxy': 'http://username:password@proxy.provider.com:port'
#     }

#     # 1. Snapshot network counters BEFORE the request
#     net_before = psutil.net_io_counters()

#     # 2. Run the yt_dlp extraction
#     with yt_dlp.YoutubeDL(ydl_opts_meta) as ydl:
#         info = ydl.extract_info(url, download=False)
#         payload_bytes = info.get('filesize_approx') or info.get('filesize') or 0

#     # 3. Snapshot network counters AFTER the request
#     net_after = psutil.net_io_counters()

#     # 4. Calculate the exact difference
#     bytes_sent = net_after.bytes_sent - net_before.bytes_sent
#     bytes_recv = net_after.bytes_recv - net_before.bytes_recv
#     total_traffic_bytes = bytes_sent + bytes_recv

#     total_gb = total_traffic_bytes / (1024**3)
#     exact_cost = total_gb * COST_PER_GB

#     duration_mins = info.get("duration") / 60

#     logger.info(f"--- Exact Network Measurement ---")
#     logger.info(f"Audio Payload Size: {payload_bytes / (1024**2):.2f} MB")
#     logger.info(f"Actual Upload:      {bytes_sent / (1024**2):.2f} MB")
#     logger.info(f"Actual Download:    {bytes_recv / (1024**2):.2f} MB")
#     logger.info(f"Total Proxy Traffic:{total_traffic_bytes / (1024**2):.2f} MB")
#     logger.info(f"Exact Proxy Cost:   ${exact_cost:.6f}")
#     if duration_mins > 0:
#         logger.info(f"total duration:     {duration_mins:.1f}min")
#         logger.info(f"Cost per minute:    ${exact_cost / duration_mins:.6f}")
#     logger.info(f"---------------------------------\n")

# if __name__ == "__main__":
#     # NOTE: Close background apps (Spotify, heavy browser tabs) 
#     # to ensure the system-wide network counters are accurate.
#     measure_exact_traffic(url="https://www.youtube.com/watch?v=UNP03fDSj1U")












# import yt_dlp
# import logging

# logging.basicConfig(level=logging.INFO, format='%(message)s')
# logger = logging.getLogger("")

# # --- Proxy Pricing and Overhead Constants ---
# COST_PER_GB = 7.50

# # Network overhead (TCP/IP headers, TLS encryption, HTTP chunking)
# # Generally adds ~4% to the raw file size over the wire.
# NETWORK_OVERHEAD_RATIO = 1.04 

# # Traffic used by yt_dlp just to extract the video URL 
# # (HTML, Player JS, and API requests). Estimated at 1.5 MB.
# YT_METADATA_OVERHEAD_BYTES = 1.5 * 1024 * 1024 

# def estimate_download_cost(url: str):
#     logger.info(f"Analyzing video: {url}")
    
#     ydl_opts_meta = {
#         'format': 'm4a/bestaudio/best',
#         'quiet': True,
#         'no_warnings': True,
#     }

#     with yt_dlp.YoutubeDL(ydl_opts_meta) as ydl:
#         info = ydl.extract_info(url, download=False)
        
#         # 1. Get Payload size (The actual audio file)
#         payload_bytes = info.get('filesize_approx') or info.get('filesize')
        
#         # Fallback: Sometimes YouTube doesn't provide the filesize in the API.
#         # We break the test to try with another video
#         if not payload_bytes:
#             logger.debug("Exact filesize missing. Stoping test")
#             return

#         # 2. Add Transport Overhead
#         transport_bytes = payload_bytes * NETWORK_OVERHEAD_RATIO

#         # 3. Add Metadata/Extraction Overhead
#         total_bytes = transport_bytes + YT_METADATA_OVERHEAD_BYTES

#         # Convert to GB and calculate cost
#         total_gb = total_bytes / (1024**3)
#         estimated_cost = total_gb * COST_PER_GB

#         # Calculate duration in minutes for cost-per-minute
#         duration_mins = info.get("duration") / 60

#         logger.info(f"--- Cost Breakdown ---")
#         logger.info(f"Audio Payload:      {payload_bytes / (1024**2):.2f} MB")
#         logger.info(f"Total Proxy Traffic:{total_bytes / (1024**2):.2f} MB (incl. 4% transport + 1.5MB metadata)")
#         logger.info(f"Estimated Cost:     ${estimated_cost:.6f}")
        
#         if duration_mins > 0:
#             logger.info(f"total duration:     {duration_mins:.1f}min")
#             logger.info(f"Cost per minute:    ${estimated_cost / duration_mins:.6f}")
#         logger.info(f"----------------------\n")


# if __name__ == "__main__":
#     logger.info("Starting estimations...\n")
#     estimate_download_cost(url="https://www.youtube.com/watch?v=UNP03fDSj1U")
#     estimate_download_cost(url="https://www.youtube.com/watch?v=Hu4Yvq-g7_Y")
#     estimate_download_cost(url="https://www.youtube.com/watch?v=zIwLWfaAg-8")
#     logger.info("Finished estimations.")






















# import os
# import tempfile
# import yt_dlp
# import requests
# import logging

# # Configure logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger("PipelineLogger")

# def download_audio_with_proxy(url: str) -> str:
#     print(f"checking video {url}")
#     ydl_opts_meta = {
#         # 'format': 'm4a/bestaudio/best',
#         'format': 'bestvideo+bestaudio/best',
#         'quiet': True,
#         'no_warnings': True,
#     }

#     with yt_dlp.YoutubeDL(ydl_opts_meta) as ydl:
#         info = ydl.extract_info(url, download=False)

#         # This gives you the estimated size in bytes
#         filesize_bytes = info.get('filesize_approx') or info.get('filesize') or 0
#         filesize_gb = filesize_bytes / (1024**3)
#         print(f"Estimated size download: {filesize_gb:.6f} GB")
#         print(f"Estimated download cost: {filesize_gb*7.5:.6f}$")
#         # print(f"Estimated download cost per minute: {(filesize_gb*7.5)/info.get("duration")}$")

#         print("----")



# if __name__ == "__main__":
#     print(f"Starting download")
#     download_audio_with_proxy(url="youtube.com/watch?v=UNP03fDSj1U&pp=ygUPc2hvcnQgdGVkIHRhbGtz")
#     download_audio_with_proxy(url="https://www.youtube.com/watch?v=Hu4Yvq-g7_Y")
#     download_audio_with_proxy(url="https://www.youtube.com/watch?v=zIwLWfaAg-8")
#     print("Finished download")