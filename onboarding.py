from typing import Dict, List, Optional, Tuple, Any
from flask import request, session, redirect, flash
import threading
import os

# Import our new modules
try:
    from .linkedin_scraper import LinkedInScraper
    from .onboarding_agent import OnboardingAgent
except ImportError:
    from linkedin_scraper import LinkedInScraper
    from onboarding_agent import OnboardingAgent



def render_photo_preview(photo_url: str) -> str:
    """Render photo preview if URL exists"""
    if photo_url and photo_url.strip():
        return f'''
        <div id="photo-preview" style="margin-top: 10px;">
            <div style="font-size: 12px; color: #666; margin-bottom: 5px;">Current photo:</div>
            <img src="{photo_url}" style="width: 100px; height: 100px; object-fit: cover; border-radius: 8px; border: 2px solid #ddd;" 
                 onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
            <div style="display: none; padding: 10px; background: #f8d7da; color: #721c24; border-radius: 4px; font-size: 12px;">
                Could not load current image.
            </div>
        </div>
        '''
    else:
        return '<div id="photo-preview"></div>'


def get_initials(name: str) -> str:
    """Get initials from name"""
    parts = name.split()
    if len(parts) >= 2:
        return parts[0][0] + parts[-1][0]
    return parts[0][0] if parts else "?"

def render_onboarding_template(step, total_steps, step_title, step_description, step_content, profile, is_last_step, render_template_with_header):
    """Render onboarding template matching dashboard aesthetic"""
    progress_percent = (step / total_steps) * 100
    
    prev_button = f'<button type="submit" name="action" value="previous" class="btn btn-secondary">← Previous</button>' if step > 1 else ''
    
    if is_last_step:
        next_button = '<button type="submit" name="action" value="complete" class="btn btn-complete">Complete Profile & Find Matches</button>'
    else:
        next_button = '<button type="submit" name="action" value="next" class="btn btn-primary">Next →</button>'
    
    # Content styled to match dashboard
    content = f'''
    <style>
        @import url("https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=sentient@400,500,600,700&display=swap");
        
        .onboarding-container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 2rem;
            min-height: 80vh;
            display: flex;
            flex-direction: column;
        }}
        
        .step-header {{
            text-align: center;
            margin-bottom: 3rem;
            padding: 2.5rem 2rem;
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}
        
        .step-counter {{
            font-family: "Satoshi", sans-serif;
            font-size: 0.875rem;
            color: black;
            margin-bottom: 0.75rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.1em;
        }}
        
        .step-title {{
            font-family: "Sentient", "Satoshi", sans-serif;
            font-size: 2.5rem;
            font-weight: 500;
            margin: 0 0 1rem 0;
            color: black;
            letter-spacing: -0.02em;
        }}
        
        .step-description {{
            font-family: "Satoshi", sans-serif;
            font-size: 1.125rem;
            line-height: 1.6;
            color: black;
            margin: 0 0 1rem 0;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }}
        
        .progress-container {{
            margin: 1.5rem 0;
        }}
        
        .progress-bar {{
            background: rgba(0, 0, 0, 0.2);
            border-radius: 12px;
            height: 8px;
            overflow: hidden;
            position: relative;
        }}
        
        .progress-fill {{
            background: black;
            height: 100%;
            border-radius: 12px;
            width: {progress_percent}%;
            transition: width 0.5s ease;
            position: relative;
        }}
        
        .progress-fill::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
            animation: shimmer 2s ease-in-out infinite;
        }}
        
        @keyframes shimmer {{
            0% {{ transform: translateX(-100%); }}
            100% {{ transform: translateX(100%); }}
        }}
        
        .step-content-wrapper {{
            flex: 1;
            margin: 1rem 0;
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 2.5rem;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}
        
        .form-group {{
            margin-bottom: 1.5rem;
        }}
        
        .form-label {{
            font-family: "Satoshi", sans-serif;
            display: block;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 0.75rem;
            opacity: 0.8;
            font-weight: 600;
            color: #2d2d2d;
        }}
        
        .form-input, .form-select, .form-textarea {{
            font-family: "Satoshi", sans-serif;
            width: 100%;
            padding: 1rem 1.25rem;
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 16px;
            color: #2d2d2d;
            font-size: 1rem;
            transition: all 0.3s ease;
            box-sizing: border-box;
        }}
        
        .form-input:focus, .form-select:focus, .form-textarea:focus {{
            outline: none;
            border-color: rgba(107, 155, 153, 0.3);
            background: rgba(255, 255, 255, 0.9);
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(107, 155, 153, 0.15);
        }}
        
        .form-input::placeholder {{
            color: rgba(45, 45, 45, 0.5);
        }}
        
        .form-select {{
            cursor: pointer;
            appearance: none;
            background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b9b99' stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
            background-position: right 1rem center;
            background-repeat: no-repeat;
            background-size: 1rem;
            padding-right: 3rem;
        }}
        
        /* Slider Styling to match dashboard */
        .slider-container {{
            margin: 1.5rem 0;
            padding: 2rem;
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            transition: all 0.3s ease;
        }}
        
        .slider-container:hover {{
            border-color: rgba(107, 155, 153, 0.3);
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(107, 155, 153, 0.15);
        }}
        
        .slider-label {{
            font-family: "Satoshi", sans-serif;
            font-weight: 600;
            margin-bottom: 1.5rem;
            color: #2d2d2d;
            font-size: 1rem;
            text-align: center;
        }}
        
        input[type=range] {{
            -webkit-appearance: none;
            appearance: none;
            width: 100%;
            height: 6px;
            border-radius: 3px;
            background: rgba(0, 0, 0, 0.2);
            outline: none;
            margin: 1.5rem 0;
        }}
        
        input[type=range]::-webkit-slider-thumb {{
            -webkit-appearance: none;
            appearance: none;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: black;
            cursor: pointer;
            border: 3px solid white;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            transition: all 0.2s ease;
        }}
        
        input[type=range]::-webkit-slider-thumb:hover {{
            transform: scale(1.1);
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.4);
        }}
        
        input[type=range]::-moz-range-thumb {{
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: black;
            cursor: pointer;
            border: 3px solid white;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }}
        
        .slider-labels {{
            display: flex;
            justify-content: space-between;
            font-family: "Satoshi", sans-serif;
            font-size: 0.8rem;
            color: black;
            margin-top: 0.5rem;
            font-weight: 500;
        }}
        
        /* Choice styling to match dashboard */
        .choice-group {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin: 1rem 0;
        }}
        
        .choice-item {{
            position: relative;
        }}
        
        .choice-item input[type="checkbox"],
        .choice-item input[type="radio"] {{
            position: absolute;
            opacity: 0;
            cursor: pointer;
        }}
        
        .choice-label {{
            font-family: "Satoshi", sans-serif;
            display: block;
            padding: 1rem 1.25rem;
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 16px;
            cursor: pointer;
            transition: all 0.3s ease;
            text-align: center;
            font-weight: 500;
            color: #2d2d2d;
        }}
        
        .choice-item input:checked + .choice-label {{
            background: black;
            color: white;
            border-color: black;
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }}
        
        .choice-label:hover {{
            border-color: rgba(0, 0, 0, 0.3);
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
        }}
        
        .navigation-controls {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 2rem;
            padding: 1.5rem 0;
            border-top: 1px solid rgba(107, 155, 153, 0.2);
        }}
        
        .btn {{
            font-family: "Satoshi", sans-serif;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 1rem 2rem;
            border-radius: 50px;
            font-weight: 600;
            font-size: 0.875rem;
            text-decoration: none;
            transition: all 0.3s ease;
            border: none;
            cursor: pointer;
            backdrop-filter: blur(10px);
        }}
        
        .btn-primary {{
            background: black;
            color: white;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        }}
        
        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }}
        
        .btn-secondary {{
            background: black;
            color: white;
            border: 1px solid black;
        }}
        
        .btn-secondary:hover {{
            background: #333;
            transform: translateY(-2px);
            border-color: black;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }}
        
        .btn-complete {{
            background: black;
            color: white;
            padding: 1.25rem 2rem;
            font-size: 1rem;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
        }}
        
        .btn-complete:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
        }}
        
        @media (max-width: 768px) {{
            .onboarding-container {{
                padding: 1rem;
            }}
            
            .step-header {{
                padding: 1.5rem 1rem;
            }}
            
            .step-title {{
                font-size: 1.75rem;
            }}
            
            .step-content-wrapper {{
                padding: 1.5rem;
            }}
            
            .choice-group {{
                grid-template-columns: 1fr;
            }}
            
            .navigation-controls {{
                flex-direction: column;
                gap: 1rem;
            }}
            
            .btn {{
                width: 100%;
                justify-content: center;
            }}
        }}
        
        /* Animation for form elements */
        .form-group {{
            animation: slideInUp 0.5s ease forwards;
            opacity: 0;
            transform: translateY(20px);
        }}
        
        .form-group:nth-child(1) {{ animation-delay: 0.1s; }}
        .form-group:nth-child(2) {{ animation-delay: 0.2s; }}
        .form-group:nth-child(3) {{ animation-delay: 0.3s; }}
        .form-group:nth-child(4) {{ animation-delay: 0.4s; }}
        .form-group:nth-child(5) {{ animation-delay: 0.5s; }}
        
        @keyframes slideInUp {{
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
    </style>
    
    <div class="onboarding-container">
        <div class="step-header">
            <div class="step-counter">Step {step} of {total_steps}</div>
            <h1 class="step-title">{step_title}</h1>
            <div class="step-description">{step_description}</div>
            
            <div class="progress-container">
                <div class="progress-bar">
                    <div class="progress-fill"></div>
                </div>
            </div>
        </div>
        
        <form method="POST" action="/onboarding/save-step">
            <div class="step-content-wrapper">
                {step_content}
            </div>
            
            <div class="navigation-controls">
                <div>{prev_button}</div>
                <div>{next_button}</div>
            </div>
        </form>
    </div>
    '''
    
    return render_template_with_header(f"Step {step}: {step_title}", content, minimal_nav=True)


def render_onboarding_step_content(step: int, profile: Dict) -> str:
    """Render content for specific onboarding step - Compressed Protocol"""
    if step == 1:
        return render_step_1_basic_info(profile)
    elif step == 2:
        return render_step_2_defining_moment(profile)
    elif step == 3:
        return render_step_3_resource_allocation(profile)
    elif step == 4:
        return render_step_4_conflict_response(profile)
    elif step == 5:
        return render_step_5_trade_off(profile)
    elif step == 6:
        return render_step_6_social_identity(profile)
    elif step == 7:
        return render_step_7_moral_dilemma(profile)
    elif step == 8:
        return render_step_8_system_trust(profile)
    elif step == 9:
        return render_step_9_stress_response(profile)
    elif step == 10:
        return render_step_10_future_values(profile)
    else:
        return '<div>Invalid step</div>'

def render_step_1_basic_info(profile: Dict) -> str:
    """Basic Information step - styled to match dashboard"""
    return f'''
    <div class="form-group">
        <label class="form-label">Age</label>
        <input type="number" name="age" required min="18" max="100"
               value="{profile.get('age', '')}" placeholder="Enter your age"
               class="form-input">
    </div>

    <div class="form-group">
        <label class="form-label">LinkedIn Profile URL (Required for enrichment)</label>
        <input type="url" name="linkedin_url" required
            value="{profile.get('linkedin_url', '')}"
            placeholder="https://www.linkedin.com/in/your-profile"
            pattern="https://(www\.)?linkedin\.com/in/[\w\-]+"
            title="Please enter a valid LinkedIn profile URL (e.g., https://linkedin.com/in/yourname)"
            class="form-input" id="linkedin-url-input">
        <div style="font-size: 12px; color: #6b9b99; margin-top: 5px; line-height: 1.4;">
            We'll scrape your profile to enrich your data with educational background, work experience, and professional insights
        </div>
    </div>

    '''

def render_slider_component(label: str, name: str, left_label: str, right_label: str, value: int = 5) -> str:
    """Render slider component matching dashboard aesthetic"""
    return f'''
    <div class="slider-container">
        <div class="slider-label">{label}</div>
        <div style="position: relative;">
            <input type="range" min="1" max="10" value="{value}" name="{name}" 
                   id="{name}_slider"
                   oninput="updateSliderBackground(this)"
                   style="background: linear-gradient(to right, #6b9b99 0%, #6b9b99 {(value-1)*11.11}%, rgba(107, 155, 153, 0.2) {(value-1)*11.11}%, rgba(107, 155, 153, 0.2) 100%);">
            <div class="slider-labels">
                <span>{left_label}</span>
                <span>{right_label}</span>
            </div>
        </div>
    </div>
    
    <script>
        function updateSliderBackground(slider) {{
            const percentage = ((slider.value - 1) / 9) * 100;
            slider.style.background = `linear-gradient(to right, #6b9b99 0%, #6b9b99 ${{percentage}}%, rgba(107, 155, 153, 0.2) ${{percentage}}%, rgba(107, 155, 153, 0.2) 100%)`;
        }}
    </script>
    '''

def render_step_2_defining_moment(profile: Dict) -> str:
    """Defining Moment - Reveals values, risk tolerance, locus of control"""
    return f'''
    <div class="form-group">
        <label class="form-label">Tell me about a decision you made that significantly changed the direction of your life. What did you choose and why?</label>
        <textarea name="defining_moment" required
                  placeholder="Describe a pivotal life decision and your reasoning..."
                  class="form-textarea" style="height: 150px;">{profile.get('defining_moment', '')}</textarea>
        <div style="font-size: 12px; color: #6b9b99; margin-top: 5px;">
            ~2 minutes. This reveals your values, risk tolerance, and self-narrative style.
        </div>
    </div>
    '''

def render_step_3_resource_allocation(profile: Dict) -> str:
    """Resource Allocation - Reveals financial priorities, risk orientation, altruism"""
    return f'''
    <div class="form-group">
        <label class="form-label">Imagine you unexpectedly received £10,000. How would you use it?</label>
        <textarea name="resource_allocation" required
                  placeholder="Describe how you would allocate this windfall and why..."
                  class="form-textarea" style="height: 120px;">{profile.get('resource_allocation', '')}</textarea>
        <div style="font-size: 12px; color: #6b9b99; margin-top: 5px;">
            ~1 minute. This reveals your financial priorities and time preference.
        </div>
    </div>
    '''

def render_radio_options(name: str, options: List[Tuple[str, str]], selected: str = '') -> str:
    """Render radio button options using choice-item styling"""
    html = ""
    for value, label in options:
        checked = 'checked' if value == selected else ''
        html += f'''
        <div class="choice-item">
            <input type="radio" name="{name}" value="{value}" {checked} id="{name}_{value}">
            <label class="choice-label" for="{name}_{value}">{label}</label>
        </div>
        '''
    return html

def render_step_4_conflict_response(profile: Dict) -> str:
    """Conflict Response - Reveals conflict style, emotional regulation, communication patterns"""
    return f'''
    <div class="form-group">
        <label class="form-label">Describe a time when you strongly disagreed with someone important to you. How did you handle it?</label>
        <textarea name="conflict_response" required
                  placeholder="Share a specific disagreement and how you navigated it..."
                  class="form-textarea" style="height: 150px;">{profile.get('conflict_response', '')}</textarea>
        <div style="font-size: 12px; color: #6b9b99; margin-top: 5px;">
            ~2 minutes. This reveals your conflict style and relationship priorities.
        </div>
    </div>
    '''

def render_step_5_trade_off(profile: Dict) -> str:
    """Trade-off Scenario - Reveals materialism vs. meaning-seeking, risk tolerance, work values"""
    return f'''
    <div class="form-group">
        <label class="form-label">If you had to choose between a job that pays well but bores you, versus one that excites you but pays barely enough to live on, which would you choose and why?</label>
        <textarea name="trade_off_scenario" required
                  placeholder="Explain your choice and the reasoning behind it..."
                  class="form-textarea" style="height: 120px;">{profile.get('trade_off_scenario', '')}</textarea>
        <div style="font-size: 12px; color: #6b9b99; margin-top: 5px;">
            ~1 minute. This reveals your materialism vs. meaning-seeking balance.
        </div>
    </div>
    '''

def render_step_6_social_identity(profile: Dict) -> str:
    """Social Identity - Reveals identity dimensions, in-group/out-group dynamics, value systems"""
    return f'''
    <div class="form-group">
        <label class="form-label">What groups or communities do you feel you belong to?</label>
        <textarea name="social_identity_groups" required
                  placeholder="List the communities you identify with (professional, cultural, hobby-based, etc.)..."
                  class="form-textarea" style="height: 120px;">{profile.get('social_identity_groups', '')}</textarea>
    </div>

    <div class="form-group">
        <label class="form-label">Which of these is most important to your sense of who you are?</label>
        <textarea name="social_identity_central" required
                  placeholder="Which community or identity is most central to you and why?..."
                  class="form-textarea" style="height: 100px;">{profile.get('social_identity_central', '')}</textarea>
        <div style="font-size: 12px; color: #6b9b99; margin-top: 5px;">
            ~2 minutes total. This reveals your social identity dimensions and value systems.
        </div>
    </div>
    '''

def render_step_7_moral_dilemma(profile: Dict) -> str:
    """Moral Dilemma - Reveals moral framework, loyalty vs. honesty, relationship boundaries"""
    return f'''
    <div class="form-group">
        <label class="form-label">A close friend asks you to lie to protect them from serious consequences they deserve. What do you do?</label>
        <textarea name="moral_dilemma" required
                  placeholder="Describe what you would do and your reasoning..."
                  class="form-textarea" style="height: 150px;">{profile.get('moral_dilemma', '')}</textarea>
        <div style="font-size: 12px; color: #6b9b99; margin-top: 5px;">
            ~2 minutes. This reveals your moral framework and relationship boundaries.
        </div>
    </div>
    '''

def render_checkbox_options_with_limit(name: str, options: List[Tuple[str, str]], 
                                       selected: List[str] = [], max_selections: int = 3) -> str:
    """Render checkbox options with selection limit using choice-item styling"""
    html = ""
    for value, label in options:
        checked = 'checked' if value in selected else ''
        html += f'''
        <div class="choice-item">
            <input type="checkbox" name="{name}" value="{value}" {checked} 
                   id="{name}_{value}"
                   onchange="limitCheckboxSelections(this, '{name}', {max_selections})">
            <label class="choice-label" for="{name}_{value}">{label}</label>
        </div>
        '''
    return html

def render_step_8_system_trust(profile: Dict) -> str:
    """System Trust - Reveals trust in institutions, perceived agency, political orientation"""
    return f'''
    <div class="form-group">
        <label class="form-label">When you think about institutions like government, healthcare, or the economy, do you generally feel they work for people like you, against you, or neither? Why?</label>
        <textarea name="system_trust" required
                  placeholder="Share your perspective on institutional trust and why you feel this way..."
                  class="form-textarea" style="height: 120px;">{profile.get('system_trust', '')}</textarea>
        <div style="font-size: 12px; color: #6b9b99; margin-top: 5px;">
            ~1 minute. This reveals your trust in institutions and perceived agency.
        </div>
    </div>
    '''

def render_ranking_items(items: List[Tuple[str, str]], profile: Dict) -> str:
    """Render ranking dropdown items with glassmorphism styling"""
    html = ""
    for name, label in items:
        selected_value = profile.get(name, '')
        options = ""
        for i in range(1, 6):
            selected = 'selected' if str(i) == selected_value else ''
            options += f'<option value="{i}" {selected}>{i}</option>'
        
        html += f'''
        <div style="display: flex; align-items: center; padding: 1rem 1.25rem; background: rgba(255, 255, 255, 0.8); backdrop-filter: blur(10px); border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.2); margin: 8px 0; transition: all 0.3s ease;" onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 8px 24px rgba(107, 155, 153, 0.15)'" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none'">
            <select name="{name}" required style="width: 60px; margin-right: 15px; padding: 8px 12px; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 12px; background: rgba(255, 255, 255, 0.9); color: #2d2d2d; font-family: 'Satoshi', sans-serif; backdrop-filter: blur(10px);">
                <option value="">#</option>
                {options}
            </select>
            <label style="flex: 1; margin: 0; color: #2d2d2d; font-family: 'Satoshi', sans-serif; font-weight: 500;">{label}</label>
        </div>
        '''
    return html

def render_checkbox_options(name: str, options: List[Tuple[str, str]], selected: List[str] = []) -> str:
    """Render checkbox options using choice-item styling"""
    html = ""
    for value, label in options:
        checked = 'checked' if value in selected else ''
        html += f'''
        <div class="choice-item">
            <input type="checkbox" name="{name}" value="{value}" {checked} id="{name}_{value}">
            <label class="choice-label" for="{name}_{value}">{label}</label>
        </div>
        '''
    return html

def render_step_9_stress_response(profile: Dict) -> str:
    """Stress Response - Reveals stress triggers, coping mechanisms, support network"""
    return f'''
    <div class="form-group">
        <label class="form-label">Tell me about the last time you felt really overwhelmed or stressed. What caused it and how did you cope?</label>
        <textarea name="stress_response" required
                  placeholder="Describe a stressful situation and how you managed it..."
                  class="form-textarea" style="height: 150px;">{profile.get('stress_response', '')}</textarea>
        <div style="font-size: 12px; color: #6b9b99; margin-top: 5px;">
            ~2 minutes. This reveals your stress triggers and coping mechanisms.
        </div>
    </div>
    '''

def process_onboarding_with_ai(user_id: int, profile_data: Dict[str, Any], user_auth) -> None:
    """
    Background task to process onboarding with AI agent and LinkedIn scraping

    Args:
        user_id: User ID
        profile_data: User's onboarding responses
        user_auth: UserAuth instance for saving data
    """
    try:
        print(f"[AI Processing] Starting onboarding processing for user {user_id}")

        # 1. Scrape LinkedIn if URL provided
        linkedin_data = None
        linkedin_url = profile_data.get('linkedin_url')

        if linkedin_url:
            print(f"[LinkedIn] Scraping profile: {linkedin_url}")

            # Initialize scraper with Fresh API
            fresh_key = os.environ.get('FRESH_API_KEY')
            scraper = LinkedInScraper(fresh_api_key=fresh_key)

            linkedin_data = scraper.scrape_profile(linkedin_url)

            if linkedin_data.get('error'):
                print(f"[LinkedIn] Scraping failed: {linkedin_data.get('error')}")
            else:
                print(f"[LinkedIn] Successfully scraped profile for {linkedin_data.get('full_name', 'Unknown')}")

        # 2. Process with AI agent
        print(f"[AI Agent] Analyzing onboarding responses...")

        # Initialize AI agent with OpenAI
        api_key = os.environ.get('OPENAI_API_KEY')
        agent = OnboardingAgent(api_key=api_key)

        # Process onboarding
        enriched_profile = agent.process_onboarding(profile_data, linkedin_data)

        # 3. Generate the final onboarding script
        print(f"[AI Agent] Generating personality profile script...")
        onboarding_script = agent.create_agent_onboarding_script(enriched_profile)

        # 4. Save enriched data back to profile
        profile_data['ai_enriched'] = True
        profile_data['linkedin_scraped_data'] = linkedin_data
        profile_data['psychological_insights'] = enriched_profile.get('psychological_insights', {})
        profile_data['agent_onboarding_script'] = onboarding_script
        profile_data['processed_at'] = enriched_profile.get('agent_metadata', {}).get('processed_at')

        user_auth.save_user_profile(user_id, profile_data)

        print(f"[AI Processing] Completed onboarding processing for user {user_id}")
        print(f"[AI Processing] Generated {len(onboarding_script)} character personality profile")

    except Exception as e:
        print(f"[AI Processing] Error processing onboarding for user {user_id}: {e}")
        import traceback
        traceback.print_exc()

        # Save error to profile for debugging
        profile_data['ai_processing_error'] = str(e)
        try:
            user_auth.save_user_profile(user_id, profile_data)
        except:
            pass


def render_step_10_future_values(profile: Dict) -> str:
    """Future Orientation & Rapid-Fire Values - Reveals goals, optimism, value hierarchy"""
    return f'''
    <div class="form-group">
        <label class="form-label">In 5 years, what do you hope will be different about your life?</label>
        <textarea name="future_orientation" required
                  placeholder="Describe your hopes and aspirations for the future..."
                  class="form-textarea" style="height: 120px;">{profile.get('future_orientation', '')}</textarea>
        <div style="font-size: 12px; color: #6b9b99; margin-top: 5px;">
            ~1 minute. This reveals your goal orientation and life priorities.
        </div>
    </div>

    <div class="form-group">
        <label class="form-label">Rapid-Fire Values: Which matters more to you?</label>
        <div style="font-size: 12px; color: #6b9b99; margin-bottom: 15px;">
            Answer quickly - first instinct is best. (~1 minute total)
        </div>

        <div style="margin-bottom: 1rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 500;">Stability or Excitement?</label>
            <div class="choice-group">
                {render_radio_options("value_stability_excitement", [
                    ("stability", "Stability"),
                    ("excitement", "Excitement")
                ], profile.get('value_stability_excitement', ''))}
            </div>
        </div>

        <div style="margin-bottom: 1rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 500;">Being liked or Being respected?</label>
            <div class="choice-group">
                {render_radio_options("value_liked_respected", [
                    ("liked", "Being liked"),
                    ("respected", "Being respected")
                ], profile.get('value_liked_respected', ''))}
            </div>
        </div>

        <div style="margin-bottom: 1rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 500;">Tradition or Innovation?</label>
            <div class="choice-group">
                {render_radio_options("value_tradition_innovation", [
                    ("tradition", "Tradition"),
                    ("innovation", "Innovation")
                ], profile.get('value_tradition_innovation', ''))}
            </div>
        </div>

        <div style="margin-bottom: 1rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 500;">Community or Independence?</label>
            <div class="choice-group">
                {render_radio_options("value_community_independence", [
                    ("community", "Community"),
                    ("independence", "Independence")
                ], profile.get('value_community_independence', ''))}
            </div>
        </div>

        <div style="margin-bottom: 1rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 500;">Fairness or Loyalty?</label>
            <div class="choice-group">
                {render_radio_options("value_fairness_loyalty", [
                    ("fairness", "Fairness"),
                    ("loyalty", "Loyalty")
                ], profile.get('value_fairness_loyalty', ''))}
            </div>
        </div>
    </div>
    '''

# ============================================================================
# ROUTES - PROFILE SETUP & ONBOARDING
# ============================================================================
def add_onboarding_routes(app, login_required, user_auth, render_template_with_header, get_db_connection, process_matching_background):

    @app.route('/profile-setup')
    @login_required 
    def profile_setup():
        """Redirect to first step of onboarding"""
        return redirect('/onboarding/step/1')

    @app.route('/onboarding/step/<int:step>')
    @login_required
    def onboarding_step(step):
        """Multi-step onboarding flow"""
        user_id = session['user_id']
        existing_profile = user_auth.get_user_profile(user_id) or {}
        session['onboarding_step'] = step
        
        # Define step configuration - Compressed Protocol
        steps_config = {
            1: {'title': 'Basic Information', 'description': 'Your foundational details and LinkedIn profile'},
            2: {'title': 'Defining Moment', 'description': 'A life-changing decision that shaped who you are'},
            3: {'title': 'Resource Allocation', 'description': 'How you would handle an unexpected windfall'},
            4: {'title': 'Conflict Response', 'description': 'How you navigate disagreements with others'},
            5: {'title': 'Trade-off Scenario', 'description': 'What you prioritize: money or meaning'},
            6: {'title': 'Social Identity', 'description': 'The communities and groups that define you'},
            7: {'title': 'Moral Dilemma', 'description': 'Your approach to difficult ethical choices'},
            8: {'title': 'System Trust', 'description': 'How you view institutions and authority'},
            9: {'title': 'Stress Response', 'description': 'How you cope with overwhelming situations'},
            10: {'title': 'Future & Values', 'description': 'Your aspirations and core value preferences'}
        }
        
        if step not in steps_config:
            return redirect('/onboarding/step/1')
        
        step_content = render_onboarding_step_content(step, existing_profile)
        config = steps_config[step]
        
        return render_onboarding_template(
            step=step,
            total_steps=10,
            step_title=config['title'],
            step_description=config['description'],
            step_content=step_content,
            profile=existing_profile,
            is_last_step=(step == 10),
            render_template_with_header=render_template_with_header
        )

    @app.route('/edit-profile', methods=['GET', 'POST'])
    @login_required
    def edit_profile():
        """Enhanced profile editing with privacy controls matching dashboard aesthetic"""
        user_id = session['user_id']
        user_info = user_auth.get_user_info(user_id)
        
        if request.method == 'POST':
            print("DEBUG: POST request started - entering form submission")
            # Handle form submission
            try:
                print("DEBUG: Inside try block, about to process form data")
                # Update basic user info
                email = request.form.get('email', '').strip()
                phone = request.form.get('phone', '').strip()
                first_name = request.form.get('first_name', '').strip()
                last_name = request.form.get('last_name', '').strip()
                print(f"DEBUG: Form submitted with first_name='{first_name}', last_name='{last_name}'")

                # Update user table
                conn = get_db_connection()
                cursor = conn.cursor()

                matching_mode = request.form.get('matching_mode', 'individual')
                print(f"DEBUG: Saving matching_mode: {matching_mode} for user {user_id}")

                # Update user table first
                print(f"DEBUG: About to execute UPDATE with values: email='{email}', phone='{phone}', first_name='{first_name}', last_name='{last_name}', matching_mode='{matching_mode}', user_id={user_id}")

                cursor.execute('''
                    UPDATE users
                    SET email = %s, phone = %s, first_name = %s, last_name = %s, matching_mode = %s
                    WHERE id = %s
                ''', (email, phone, first_name, last_name, matching_mode, user_id))

                rows_affected = cursor.rowcount
                print(f"DEBUG: UPDATE query affected {rows_affected} rows")

                # Commit user table changes first
                conn.commit()
                print("DEBUG: Database changes committed")
                conn.close()

                # Get existing profile data AFTER committing user changes
                existing_profile = user_auth.get_user_profile(user_id) or {}

                # Update profile data
                existing_profile.update({
                    'bio': request.form.get('bio', '').strip(),
                    'postcode': request.form.get('postcode', '').strip(),
                    'profile_photo_url': request.form.get('profile_photo_url', '').strip(),
                    'matching_mode': matching_mode,
                    'linkedin_url': request.form.get('linkedin_url', '').strip(),
                })

                # Save updated profile
                user_auth.save_user_profile(user_id, existing_profile)
                print(f"DEBUG: Profile saved with matching_mode: {existing_profile.get('matching_mode')}")

                flash('Profile updated successfully!', 'success')
                return redirect('/edit-profile')

            except Exception as e:
                print(f"Error updating profile: {e}")
                import traceback
                traceback.print_exc()

                # Make sure to close connection on error
                try:
                    if 'conn' in locals():
                        conn.close()
                except:
                    pass

                flash('Error updating profile. Please try again.', 'error')
                return redirect('/edit-profile')
        
        # GET request - show edit form
        # Get fresh user info to ensure we have the latest database values
        user_info = user_auth.get_user_info(user_id)
        print(f"DEBUG: GET request - user_info: first_name='{user_info.get('first_name', '')}', last_name='{user_info.get('last_name', '')}'")

        existing_profile = user_auth.get_user_profile(user_id) or {}
        privacy_settings = existing_profile.get('privacy_settings', {})
        
        content = f'''
        <style>
            @import url("https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=sentient@400,500,600,700&display=swap");
            
            .edit-profile-container {{
                max-width: 900px;
                margin: 0 auto;
                padding: 2rem;
                font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, sans-serif;
            }}
            
            .profile-header {{
                text-align: center;
                margin-bottom: 3rem;
                padding: 2.5rem 2rem;
                background: rgba(255, 255, 255, 0.7);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                position: relative;
            }}
            
            .profile-header::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 1px;
                background: linear-gradient(90deg, transparent, var(--color-sage), transparent);
            }}
            
            .profile-title {{
                font-family: "Sentient", "Satoshi", sans-serif;
                font-size: 2.5rem;
                font-weight: 500;
                margin: 0 0 1rem 0;
                color: black;
                letter-spacing: -0.02em;
            }}
            
            .profile-subtitle {{
                font-family: "Satoshi", sans-serif;
                font-size: 1.125rem;
                line-height: 1.6;
                color: black;
                margin: 0;
            }}
            
            .form-section {{
                background: rgba(255, 255, 255, 0.9);
                backdrop-filter: blur(20px);
                border-radius: 24px;
                padding: 2.5rem;
                margin: 2rem 0;
                border: 1px solid rgba(255, 255, 255, 0.2);
                transition: all 0.3s ease;
            }}
            
            .form-section:hover {{
                transform: translateY(-2px);
                border-color: rgba(107, 155, 153, 0.3);
                box-shadow: 0 8px 32px rgba(0,0,0,0.08);
            }}
            
            .section-title {{
                font-family: "Sentient", "Satoshi", sans-serif;
                font-size: 1.5rem;
                font-weight: 600;
                margin: 0 0 1.5rem 0;
                color: var(--color-charcoal);
                display: flex;
                align-items: center;
                gap: 0.75rem;
            }}
            
            .section-icon {{
                font-size: 1.25rem;
            }}
            
            .form-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 1.5rem;
                margin-bottom: 1.5rem;
            }}
            
            .form-group {{
                margin-bottom: 1.5rem;
            }}
            
            .form-label {{
                font-family: "Satoshi", sans-serif;
                display: block;
                font-size: 0.75rem;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                margin-bottom: 0.75rem;
                opacity: 0.8;
                font-weight: 600;
                color: var(--color-charcoal);
            }}
            
            .form-input, .form-textarea {{
                font-family: "Satoshi", sans-serif;
                width: 100%;
                padding: 1rem 1.25rem;
                background: rgba(255, 255, 255, 0.8);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 16px;
                color: var(--color-charcoal);
                font-size: 1rem;
                transition: all 0.3s ease;
                box-sizing: border-box;
            }}
            
            .form-input:focus, .form-textarea:focus {{
                outline: none;
                border-color: rgba(107, 155, 153, 0.5);
                background: rgba(255, 255, 255, 0.95);
                transform: translateY(-2px);
                box-shadow: 0 8px 24px rgba(107, 155, 153, 0.15);
            }}
            
            .form-input::placeholder, .form-textarea::placeholder {{
                color: rgba(45, 45, 45, 0.5);
            }}
            
            .form-textarea {{
                resize: vertical;
                min-height: 100px;
                line-height: 1.6;
            }}
            
            .form-help {{
                font-size: 0.75rem;
                color: rgba(107, 155, 153, 0.8);
                margin-top: 0.5rem;
                line-height: 1.4;
            }}
            
            .photo-preview-container {{
                margin-top: 1rem;
                padding: 1rem;
                background: rgba(107, 155, 153, 0.1);
                border-radius: 12px;
                border: 1px dashed rgba(107, 155, 153, 0.3);
            }}
            
            .photo-preview {{
                display: none;
            }}
            
            .photo-preview.active {{
                display: block;
            }}
            
            .preview-image {{
                width: 120px;
                height: 120px;
                object-fit: cover;
                border-radius: 12px;
                border: 2px solid rgba(107, 155, 153, 0.3);
                display: block;
                margin: 0 auto;
            }}
            
            .preview-label {{
                font-size: 0.75rem;
                color: var(--color-gray-600);
                text-align: center;
                margin-bottom: 0.5rem;
                font-weight: 500;
            }}
            
            .preview-error {{
                background: rgba(255, 149, 0, 0.1);
                border: 1px solid rgba(255, 149, 0, 0.3);
                color: #ff9500;
                padding: 0.75rem;
                border-radius: 8px;
                font-size: 0.75rem;
                text-align: center;
            }}
            
            .privacy-section {{
                background: linear-gradient(135deg, var(--color-sage), var(--color-lavender));
                color: var(--color-charcoal);
                padding: 2.5rem;
                border-radius: 24px;
                margin: 2rem 0;
            }}
            
            .privacy-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 1rem;
                margin-top: 1.5rem;
            }}
            
            .privacy-item {{
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 1rem;
                background: rgba(255, 255, 255, 0.8);
                border-radius: 12px;
                backdrop-filter: blur(10px);
            }}
            
            .privacy-checkbox {{
                width: 20px;
                height: 20px;
                border: 2px solid rgba(107, 155, 153, 0.5);
                border-radius: 4px;
                background: transparent;
                cursor: pointer;
                position: relative;
                flex-shrink: 0;
            }}
            
            .privacy-checkbox:checked {{
                background: var(--color-emerald);
                border-color: var(--color-emerald);
            }}
            
            .privacy-checkbox:checked::after {{
                content: '✓';
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                color: white;
                font-size: 12px;
                font-weight: 600;
            }}
            
            .privacy-label {{
                font-size: 0.875rem;
                font-weight: 500;
                cursor: pointer;
                line-height: 1.4;
            }}
            
            .action-buttons {{
                display: flex;
                gap: 1.5rem;
                justify-content: center;
                margin: 3rem 0 2rem 0;
                flex-wrap: wrap;
            }}
            
            .btn {{
                font-family: "Satoshi", sans-serif;
                display: inline-flex;
                align-items: center;
                gap: 0.5rem;
                padding: 1rem 2rem;
                border-radius: 50px;
                font-weight: 600;
                font-size: 0.875rem;
                text-decoration: none;
                transition: all 0.3s ease;
                border: none;
                cursor: pointer;
                backdrop-filter: blur(10px);
                white-space: nowrap;
            }}
            
            .btn-primary {{
                background: black;
                color: white;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
            }}
            
            .btn-primary:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
            }}
            
            .btn-secondary {{
                background: black;
                color: white;
                border: 1px solid black;
            }}
            
            .btn-secondary:hover {{
                background: #333;
                transform: translateY(-2px);
                border-color: black;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            }}
            
            .rematching-section {{
                background: black;
                color: white;
                padding: 2.5rem;
                border-radius: 24px;
                text-align: center;
                margin-top: 3rem;
                position: relative;
                overflow: hidden;
            }}
            
            .rematching-section::before {{
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
                animation: shimmer 3s ease-in-out infinite;
            }}
            
            @keyframes shimmer {{
                0% {{ left: -100%; }}
                50% {{ left: 100%; }}
                100% {{ left: 100%; }}
            }}
            
            .rematching-title {{
                font-family: "Sentient", "Satoshi", sans-serif;
                font-size: 1.5rem;
                font-weight: 600;
                margin-bottom: 1rem;
            }}
            
            .rematching-description {{
                font-size: 1rem;
                line-height: 1.6;
                margin-bottom: 2rem;
                opacity: 0.9;
            }}
            
            .btn-rematch {{
                background: white;
                color: black;
                padding: 1.25rem 2rem;
                font-size: 1rem;
                font-weight: 600;
                border: 2px solid white;
            }}
            
            .btn-rematch:hover {{
                background: #f0f0f0;
                color: black;
                transform: translateY(-2px);
                box-shadow: 0 8px 24px rgba(255, 255, 255, 0.4);
            }}
            
            /* Flash Messages */
            .flash-messages {{
                margin-bottom: 2rem;
            }}
            
            .flash-success {{
                background: rgba(107, 155, 153, 0.9);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(107, 155, 153, 0.5);
                color: white;
                padding: 1rem 1.5rem;
                border-radius: 12px;
                margin-bottom: 1rem;
                font-family: "Satoshi", sans-serif;
                font-size: 0.875rem;
            }}
            
            .flash-error {{
                background: rgba(255, 149, 0, 0.9);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 149, 0, 0.5);
                color: white;
                padding: 1rem 1.5rem;
                border-radius: 12px;
                margin-bottom: 1rem;
                font-family: "Satoshi", sans-serif;
                font-size: 0.875rem;
            }}
            
            /* Responsive Design */
            @media (max-width: 768px) {{
                .edit-profile-container {{
                    padding: 1rem;
                }}
                
                .profile-header {{
                    padding: 1.5rem 1rem;
                }}
                
                .profile-title {{
                    font-size: 1.75rem;
                }}
                
                .form-section {{
                    padding: 1.5rem;
                }}
                
                .form-grid {{
                    grid-template-columns: 1fr;
                    gap: 1rem;
                }}
                
                .privacy-grid {{
                    grid-template-columns: 1fr;
                }}
                
                .action-buttons {{
                    flex-direction: column;
                    align-items: center;
                    gap: 1rem;
                }}
                
                .btn {{
                    width: 100%;
                    max-width: 280px;
                    justify-content: center;
                }}
            }}
            
            /* Animation for sections */
            .form-section {{
                animation: slideInUp 0.5s ease forwards;
                opacity: 0;
                transform: translateY(20px);
            }}
            
            .form-section:nth-child(2) {{ animation-delay: 0.1s; }}
            .form-section:nth-child(3) {{ animation-delay: 0.2s; }}
            .form-section:nth-child(4) {{ animation-delay: 0.3s; }}
            .form-section:nth-child(5) {{ animation-delay: 0.4s; }}
            
            @keyframes slideInUp {{
                to {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
        </style>
        
        <div class="edit-profile-container">
            
            
            <div class="profile-header">
                <h1 class="profile-title">Edit Your Profile</h1>
                <p class="profile-subtitle">Update your information and privacy settings</p>
            </div>
            
            <form method="POST" enctype="multipart/form-data">
                <!-- Basic Information Section -->
                <div class="form-section">
                    <h2 class="section-title">
                        Basic Information
                    </h2>
                    
                    <div class="form-grid">
                        <div class="form-group">
                            <label class="form-label" for="first_name">First Name</label>
                            <input type="text" name="first_name" id="first_name" 
                                value="{user_info.get('first_name', '')}" required
                                class="form-input" placeholder="Enter your first name">
                        </div>
                        <div class="form-group">
                            <label class="form-label" for="last_name">Last Name</label>
                            <input type="text" name="last_name" id="last_name"
                                value="{user_info.get('last_name', '')}" required
                                class="form-input" placeholder="Enter your last name">
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label" for="email">Email Address</label>
                        <input type="email" name="email" id="email"
                            value="{user_info.get('email', '')}" required
                            class="form-input" placeholder="your@email.com">
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label" for="phone">Contact Number</label>
                        <input type="tel" name="phone" id="phone"
                            value="{user_info.get('phone', '')}" required
                            class="form-input" placeholder="+44 7XXX XXXXXX">
                        <div class="form-help">Used for contact requests when matches want to connect</div>
                    </div>
                </div>
                <!-- Mode Selection Section 
   
                <div class="form-section">
                    <h2 class="section-title">
                        Connection Mode
                    </h2>

                    <div class="form-group">
                        <label class="form-label">How would you like to use Connect?</label>
                        <div class="choice-container">
                            <div class="choice-item">
                                <input type="radio" name="matching_mode" value="individual" {'checked' if existing_profile.get('matching_mode', 'individual') == 'individual' else ''} id="mode_individual">
                                <label class="choice-label" for="mode_individual">
                                    <strong>Individual Mode</strong>
                                    <span style="display: block; font-size: 12px; color: #666; margin-top: 4px;">Find individual friends based on compatibility</span>
                                </label>
                            </div>
                            <div class="choice-item">
                                <input type="radio" name="matching_mode" value="network" {'checked' if existing_profile.get('matching_mode', 'individual') == 'network' else ''} id="mode_network">
                                <label class="choice-label" for="mode_network">
                                    <strong>Network Mode</strong>
                                    <span style="display: block; font-size: 12px; color: #666; margin-top: 4px;">Build and manage social networks for groups</span>
                                </label>
                            </div>
                        </div>
                    </div>
                </div>
                -->
                <!-- Location Section -->
                <div class="form-section">
                    <h2 class="section-title">
                        Location
                    </h2>
                    
                    <div class="form-grid">
                        
                        <div class="form-group">
                            <label class="form-label" for="postcode">Postcode</label>
                            <input type="text" name="postcode" id="postcode"
                                value="{existing_profile.get('postcode', '')}" required
                                class="form-input" placeholder="e.g., SW3 4HN">
                        </div>
                    </div>
                </div>
                
                <!-- Personal Details Section -->
                <div class="form-section">
                    <h2 class="section-title">
                        About You
                    </h2>
                    
                    <div class="form-group">
                        <label class="form-label" for="bio">Bio / Personal Description</label>
                        <textarea name="bio" id="bio" class="form-textarea"
                                placeholder="Tell potential matches about yourself, your interests, what you're looking for in a friendship...">{existing_profile.get('bio', '')}</textarea>
                        <div class="form-help">This helps matches get to know you better before connecting</div>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label" for="profile_photo_url">Profile Photo URL (Optional)</label>
                        <input type="url" name="profile_photo_url" id="profile_photo_url"
                            value="{existing_profile.get('profile_photo_url', '')}"
                            class="form-input" 
                            placeholder="https://example.com/your-photo.jpg"
                            oninput="updatePhotoPreview()">
                        <div class="form-help">
                            Upload your photo to a service like Imgur, Google Drive (public), or use a social media photo URL
                        </div>
                        
                        <div class="photo-preview-container">
                            <div id="photo-preview">
                                {render_photo_preview(existing_profile.get('profile_photo_url', ''))}
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="form-group">
                    <label class="form-label" for="linkedin_url">LinkedIn Profile URL (Optional)</label>
                    <input type="url" name="linkedin_url" id="linkedin_url"
                        value="{existing_profile.get('linkedin_url', '')}"
                        class="form-input" 
                        placeholder="https://www.linkedin.com/in/your-profile">
                    <div class="form-help">We'll use this to enhance your professional compatibility matching</div>
                </div>
                
                <!-- Action Buttons -->
                <div class="action-buttons">
                    <a href="/dashboard" class="btn btn-secondary">Cancel Changes</a>
                    <button type="submit" class="btn btn-primary">
                        Save Profile Updates
                    </button>
                </div>

                <!-- Reset Profile Section -->
                <div class="rematching-section">
                    <h3 class="rematching-title">Want to Start Fresh?</h3>
                    <p class="rematching-description">
                        Reset your entire profile and go through the onboarding process again.
                        This will clear all your current profile data and allow you to rebuild from scratch.
                    </p>
                    <a href="/onboarding/step/1" class="btn btn-rematch">
                        Reset Profile & Start Over
                    </a>
                </div>
            </form>
            
            
        </div>
        
        <script>
            function updatePhotoPreview() {{
                const url = document.getElementById('profile_photo_url').value;
                const preview = document.getElementById('photo-preview');
                
                if (!url.trim()) {{
                    preview.innerHTML = '';
                    return;
                }}
                
                const isImageUrl = /\.(jpg|jpeg|png|gif|webp)$/i.test(url) || 
                                url.includes('imgur.com') || 
                                url.includes('drive.google.com');
                
                if (isImageUrl) {{
                    preview.innerHTML = `
                        <div class="photo-preview active">
                            <div class="preview-label">Preview:</div>
                            <img src="${{url}}" class="preview-image" 
                                onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                            <div class="preview-error" style="display: none;">
                                Could not load image. Please check the URL.
                            </div>
                        </div>
                    `;
                }} else {{
                    preview.innerHTML = `
                        <div class="preview-error">
                            Please enter a direct image URL (ending in .jpg, .png, etc.)
                        </div>
                    `;
                }}
            }}
            
            // Initialize preview on page load
            document.addEventListener('DOMContentLoaded', () => {{
                updatePhotoPreview();
            }});
            
            // Enhanced form validation
            document.querySelector('form').addEventListener('submit', function(e) {{
                const requiredFields = ['first_name', 'last_name', 'email', 'phone'];
                let isValid = true;
                
                requiredFields.forEach(field => {{
                    const input = document.getElementById(field);
                    if (!input.value.trim()) {{
                        input.style.borderColor = 'rgba(255, 149, 0, 0.5)';
                        input.style.background = 'rgba(255, 149, 0, 0.1)';
                        isValid = false;
                        
                        setTimeout(() => {{
                            input.style.borderColor = '';
                            input.style.background = '';
                        }}, 3000);
                    }}
                }});
                
                if (!isValid) {{
                    e.preventDefault();
                    alert('Please fill in all required fields.');
                }}
            }});
        </script>
        '''
        
        return render_template_with_header("Edit Profile", content, user_info)

    @app.route('/onboarding/save-step', methods=['POST'])
    @login_required
    def save_onboarding_step():
        """Save current step data and redirect to next step with proper numeric conversion"""
        user_id = session['user_id']
        current_step = session.get('onboarding_step', 1)
        
        # Get existing profile data or create new
        profile_data = user_auth.get_user_profile(user_id) or {}
        
        # Define which fields should be converted to integers
        INTEGER_FIELDS = {
            'age', 'social_energy', 'decision_making', 'communication_depth',
            'personal_growth', 'social_satisfaction', 'success_definition',
            'energy_patterns', 'activity_investment', 'time_allocation',
            'relationship_priorities', 'conflict_resolution', 'emotional_support',
            'friend_maintenance', 'community_involvement', 'work_life_philosophy',
            'future_orientation', 'social_setting', 'physical_activity',
            'cultural_consumption', 'celebration_preference', 'personal_sharing',
            'social_overlap', 'advice_giving', 'social_commitment',
            'friendship_development', 'social_risk_tolerance',
            'conflict_approach', 'life_pace',
            # Ranking fields
            'rank_shared_values', 'rank_lifestyle_rhythms', 'rank_complementary_strengths',
            'rank_emotional_compatibility', 'rank_activity_overlap'
        }
        
        # Define which fields should be converted to floats (if any)
        FLOAT_FIELDS = {
            'latitude', 'longitude'  # example location fields if you add them
        }
        
        def convert_form_data(form_data):
            """Convert form data to appropriate numeric types"""
            converted_data = {}
            
            for key, value in form_data.items():
                if key.startswith('csrf_') or key in ['action']:
                    continue
                elif key in INTEGER_FIELDS:
                    try:
                        converted_data[key] = int(value) if value else 5  # default to 5
                    except (ValueError, TypeError):
                        converted_data[key] = 5  # fallback default
                elif key in FLOAT_FIELDS:
                    try:
                        converted_data[key] = float(value) if value else 0.0
                    except (ValueError, TypeError):
                        converted_data[key] = 0.0
                else:
                    # Keep as string for text fields
                    converted_data[key] = value
            
            return converted_data
        
        # Update profile with converted form data from current step
        for key, value in request.form.items():
            if key.startswith('csrf_') or key in ['action']:
                continue
            if key in ['interests', 'personality_traits', 'red_flags', 'transportation']:
                profile_data[key] = request.form.getlist(key)
            else:
                # Convert to appropriate type
                if key in INTEGER_FIELDS:
                    try:
                        profile_data[key] = int(value) if value else 5
                    except (ValueError, TypeError):
                        profile_data[key] = 5
                elif key in FLOAT_FIELDS:
                    try:
                        profile_data[key] = float(value) if value else 0.0
                    except (ValueError, TypeError):
                        profile_data[key] = 0.0
                else:
                    profile_data[key] = value
        
        # Save updated profile
        user_auth.save_user_profile(user_id, profile_data)
        
        # Handle navigation
        action = request.form.get('action', 'next')
        
        if action == 'next':
            next_step = current_step + 1
            if next_step > 10:  # Last step
                return redirect('/onboarding/complete')
            return redirect(f'/onboarding/step/{next_step}')
        elif action == 'previous':
            prev_step = max(1, current_step - 1)
            return redirect(f'/onboarding/step/{prev_step}')
        elif action == 'complete':
            return redirect('/onboarding/complete')
        
        return redirect(f'/onboarding/step/{current_step}')

    @app.route('/onboarding/complete', methods=['GET', 'POST'])
    @login_required
    def complete_onboarding_enhanced():
        """Enhanced onboarding completion with AI processing and LinkedIn enrichment"""
        user_id = session['user_id']

        if request.method == 'POST':
            # Process final submission and blocked users (same as before)
            blocked_emails = request.form.get('blocked_emails', '')
            blocked_names = request.form.get('blocked_names', '')
            blocked_phones = request.form.get('blocked_phones', '')

            # Clear existing blocked users
            user_auth.clear_blocked_users(user_id)

            # Add new blocked users and track blocking interactions
            if blocked_emails:
                for email in [e.strip() for e in blocked_emails.split(',') if e.strip()]:
                    user_auth.add_blocked_user(user_id, blocked_email=email)
                    # Note: We can't get user_id from email easily, so this tracking is limited

            if blocked_names:
                for name in [n.strip() for n in blocked_names.split(',') if n.strip()]:
                    user_auth.add_blocked_user(user_id, blocked_name=name)

            if blocked_phones:
                for phone in [p.strip() for p in blocked_phones.split(',') if p.strip()]:
                    user_auth.add_blocked_user(user_id, blocked_phone=phone)

            # Process onboarding with AI agent in background
            profile_data = user_auth.get_user_profile(user_id)
            if profile_data:
                thread = threading.Thread(
                    target=process_onboarding_with_ai,
                    args=(user_id, profile_data, user_auth)
                )
                thread.daemon = True
                thread.start()

            # Clear onboarding session data
            session.pop('onboarding_step', None)

            # Redirect to create organization page
            return redirect('/create-organization')
        
        # Show completion page with dashboard aesthetic
        content = '''
        <style>
            @import url("https://fonts.googleapis.com/css2?family=Clash+Display:wght@200..700&display=swap");
            @import url("https://fonts.googleapis.com/css2?family=Satoshi:wght@300..900&display=swap");
            
            .completion-container {
                max-width: 600px;
                margin: 0 auto;
                padding: 2rem;
                text-align: center;
            }
            
            .completion-header {
                text-align: center;
                margin-bottom: 3rem;
                padding: 2.5rem 2rem;
                background: rgba(255, 255, 255, 0.7);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            
            .completion-title {
                font-family: "Sentient", "Satoshi", sans-serif;
                font-size: 2.5rem;
                font-weight: 500;
                margin: 0 0 1rem 0;
                color: #2d2d2d;
                letter-spacing: -0.02em;
                background: linear-gradient(135deg, #6b9b99, #ff9500);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            
            .completion-subtitle {
                font-family: "Satoshi", sans-serif;
                font-size: 1.125rem;
                line-height: 1.6;
                color: black;
                margin: 0 0 1rem 0;
            }
            
            .block-list-section {
                background: rgba(255, 255, 255, 0.9);
                backdrop-filter: blur(20px);
                border-radius: 24px;
                padding: 2.5rem;
                margin: 2rem 0;
                border: 1px solid rgba(255, 255, 255, 0.2);
                text-align: left;
                transition: all 0.3s ease;
            }
            
            .block-list-section:hover {
                transform: translateY(-4px);
                border-color: rgba(107, 155, 153, 0.3);
            }
            
            .block-list-title {
                font-family: "Sentient", "Satoshi", sans-serif;
                font-size: 1.25rem;
                font-weight: 600;
                color: #2d2d2d;
                margin-bottom: 1rem;
            }
            
            .block-list-description {
                font-family: "Satoshi", sans-serif;
                font-size: 0.875rem;
                color: black;
                margin-bottom: 1.5rem;
                line-height: 1.6;
            }
            
            .form-group {
                margin-bottom: 1.5rem;
            }
            
            .form-label {
                font-family: "Satoshi", sans-serif;
                display: block;
                font-size: 0.75rem;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                margin-bottom: 0.75rem;
                opacity: 0.8;
                font-weight: 600;
                color: #2d2d2d;
            }
            
            .form-textarea {
                font-family: "Satoshi", sans-serif;
                width: 100%;
                padding: 1rem 1.25rem;
                background: rgba(255, 255, 255, 0.8);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 16px;
                color: #2d2d2d;
                font-size: 1rem;
                transition: all 0.3s ease;
                box-sizing: border-box;
                resize: vertical;
                min-height: 80px;
            }
            
            .form-textarea:focus {
                outline: none;
                border-color: rgba(107, 155, 153, 0.3);
                background: rgba(255, 255, 255, 0.9);
                transform: translateY(-2px);
                box-shadow: 0 8px 24px rgba(107, 155, 153, 0.15);
            }
            
            .form-textarea::placeholder {
                color: rgba(45, 45, 45, 0.5);
                font-family: "Satoshi", sans-serif;
            }
            
            .launch-button {
                font-family: "Satoshi", sans-serif;
                background: linear-gradient(135deg, #6b9b99, #ff9500);
                color: white;
                border: none;
                padding: 1.25rem 2.5rem;
                border-radius: 50px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                backdrop-filter: blur(10px);
                box-shadow: 0 4px 16px rgba(107, 155, 153, 0.3);
                margin-top: 2rem;
            }
            
            .launch-button:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 24px rgba(107, 155, 153, 0.4);
            }
            
            .launch-button:active {
                transform: translateY(-1px);
            }
            
            @media (max-width: 768px) {
                .completion-container {
                    padding: 1rem;
                }
                
                .completion-header {
                    padding: 1.5rem 1rem;
                }
                
                .completion-title {
                    font-size: 1.75rem;
                }
                
                .block-list-section {
                    padding: 1.5rem;
                }
                
                .launch-button {
                    width: 100%;
                    padding: 1.5rem 2rem;
                }
            }
            
            /* Animation for form elements */
            .form-group {
                animation: slideInUp 0.5s ease forwards;
                opacity: 0;
                transform: translateY(20px);
            }
            
            .form-group:nth-child(1) { animation-delay: 0.1s; }
            .form-group:nth-child(2) { animation-delay: 0.2s; }
            .form-group:nth-child(3) { animation-delay: 0.3s; }
            
            @keyframes slideInUp {
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
        </style>
        
        <div class="completion-container">
            <div class="completion-header">
                <h1 class="completion-title">Profile Complete!</h1>
                <p class="completion-subtitle">Ready to create your organization and start simulations</p>
            </div>

            <form method="POST">
                <div class="block-list-section">
                    <h3 class="block-list-title">Privacy Controls (Optional)</h3>
                    <p class="block-list-description">
                        Optionally exclude specific people from your organization. This data is kept completely private.
                    </p>
                    
                    <div class="form-group">
                        <label class="form-label">Email addresses to exclude</label>
                        <textarea name="blocked_emails"
                                placeholder="Enter email addresses separated by commas"
                                class="form-textarea"></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Names to exclude</label>
                        <textarea name="blocked_names"
                                placeholder="Enter full names separated by commas"
                                class="form-textarea"></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Phone numbers to exclude</label>
                        <textarea name="blocked_phones"
                                placeholder="Enter phone numbers separated by commas"
                                class="form-textarea"></textarea>
                    </div>
                </div>
                
                <button type="submit" class="launch-button">
                    Continue to Create Organization
                </button>
            </form>
        </div>
        '''
        
        return render_template_with_header("Complete Profile", content, minimal_nav=True)

