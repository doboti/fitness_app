# Exercise Image Mapping Reference

## Active Workout View Updates

### Image Mapping Logic

The following exercise names are automatically mapped to their corresponding image files:

| Exercise Name | Image File |
|---------------|------------|
| Standard Push-up | `push-up.png` |
| Incline Push-up | `incline-push-up.png` |
| Incline Push-up or Dolphin Plank | `incline-push-up.png` |
| Standard Plank | `plank.png` |
| Plank to Failure | `plank.png` |
| Prone Cobra | `prone-cobra.png` |
| Standard Sit-up | `sit-up.png` |
| Air Squat | `squat.png` |
| Walking Lunge | `lunge.png` |
| Reverse Lunge | `lunge.png` |
| Standing Calf Raise | `calf-raise.png` |
| Plank Hip Dips | `plank-dips.png` |
| Dolphin Plank | `dolphin-plank.png` |
| Lying Leg Raise | `leg-raise.png` |
| Superman Hold | `superman.png` |
| High Knees | `high-knees.png` |
| Russian Twist | `russian-twist.png` |
| Squat to Cross-Body Knee Drive | `squat-knee-drive.png` |

### Layout Features

#### Thumbnail Styling
- **Size**: 80x80px (w-20 h-20)
- **Background**: Dark slate (bg-slate-900)
- **Border**: Subtle slate border (border-slate-700)
- **Corners**: Rounded (rounded-lg)
- **Padding**: 4px inside (p-1)
- **Fit**: Object-contain for proper scaling

#### Responsive Layout
- **Mobile**: Vertical stack (thumbnail above text)
- **Desktop**: Horizontal flex (thumbnail left, text middle, button right)
- **Alignment**: Items aligned to start with proper spacing

#### Fallback Mechanism
If an image fails to load:
1. The image is hidden
2. A fallback div appears with:
   - Exercise initials (first 2 words, first letter each)
   - Emerald color text
   - Bold, large font
   - Centered in the same 80x80px container

### Example Fallbacks
- "Standard Push-up" → "SP"
- "Air Squat" → "AS"
- "Lying Leg Raise" → "LL"
- "Russian Twist" → "RT"

This ensures the UI never breaks even if images are temporarily missing!
