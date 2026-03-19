class GenerateFingerprintCommand:
    @staticmethod
    def calculate_wpm(segments):
        """Calculate Words Per Minute across all segments."""
        total_words = 0
        total_duration_minutes = 0
        
        for segment in segments:
            text = segment.get("text", "")
            words = len(text.split())
            total_words += words
            
            duration_sec = segment.get("end", 0) - segment.get("start", 0)
            total_duration_minutes += duration_sec / 60.0
            
        if total_duration_minutes == 0:
            return 0.0
            
        return total_words / total_duration_minutes

    @staticmethod
    def calculate_turn_velocity(segments, duration):
        """Calculate speaker turns per minute."""
        if not segments or duration == 0:
            return 0.0
            
        turns = 0
        last_speaker = None
        
        for segment in segments:
            speaker = segment.get("speaker")
            if speaker and speaker != last_speaker:
                turns += 1
                last_speaker = speaker
                
        duration_minutes = duration / 60.0
        return turns / duration_minutes

    @staticmethod
    def calculate_overlap_ratio(segments, duration):
        """Calculate the ratio of time where multiple speakers are talking."""
        if not segments or duration == 0:
            return 0.0
            
        # Sort segments by start time
        sorted_segments = sorted(segments, key=lambda x: x["start"])
        
        total_overlap_sec = 0
        
        for i in range(1, len(sorted_segments)):
            prev = sorted_segments[i-1]
            curr = sorted_segments[i]
            
            # If current start is before previous end, we have overlap
            if curr["start"] < prev["end"]:
                overlap_end = min(prev["end"], curr["end"])
                overlap_duration = overlap_end - curr["start"]
                if overlap_duration > 0:
                    total_overlap_sec += overlap_duration
                    
        return total_overlap_sec / duration
